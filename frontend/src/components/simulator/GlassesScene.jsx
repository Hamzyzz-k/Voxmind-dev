import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { PARTS, buildGlasses, disposeGlasses } from "./glassesModel";

/** Interactive 3D view of the glasses: orbit, zoom, explode, click to select.
 *
 * The whole three.js world lives inside one effect with closure-local
 * variables, and the render loop reads its inputs from a ref box rather than
 * from props directly. Both choices are deliberate:
 *
 *   - Closure-local, not refs on the component, for the same reason
 *     CameraView.jsx does it: StrictMode mounts, cleans up, then mounts again
 *     in development. Anything shared across those instances lets the second
 *     mount corrupt the first one's teardown. This codebase has already lost
 *     time to that twice (OptionWheel, CameraView).
 *   - A ref box for the live inputs, because rebuilding a WebGL context and a
 *     whole model every time the explode slider moves would be absurd. The
 *     effect runs once; the animation loop reads the current values each
 *     frame.
 */
export default function GlassesScene({ explode, selectedId, onSelect, autoRotate, resetSignal }) {
  const mountRef = useRef(null);

  // Live inputs for the render loop. Written on every render, read at 60fps.
  const inputs = useRef({ explode, selectedId, autoRotate });
  inputs.current = { explode, selectedId, autoRotate };

  // Kept in a ref so the reset effect below can reach the controls without
  // re-running the setup effect.
  const resetRef = useRef(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    let disposed = false;
    let frameId = null;

    const scene = new THREE.Scene();

    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 200);
    // Filled in once the model exists and its real size is known.
    const HOME_POSITION = new THREE.Vector3();

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(mount.clientWidth, mount.clientHeight, false);
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.style.display = "block";
    renderer.domElement.setAttribute("aria-hidden", "true");
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.autoRotateSpeed = 1.1;
    // Zoom limits are set from the model's measured size, below.
    controls.target.set(0, 0, 0);
    resetRef.current = () => {
      camera.position.copy(HOME_POSITION);
      controls.target.set(0, 0, 0);
      controls.update();
    };

    // Three lights, each doing a specific job: a fill so nothing is pure
    // black, a key from the front-right for form, and a cool rim from behind
    // to separate the dark frame from a dark background.
    scene.add(new THREE.AmbientLight(0xffffff, 0.75));
    const key = new THREE.DirectionalLight(0xffffff, 1.5);
    key.position.set(8, 12, 14);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0x8ab4ff, 0.9);
    rim.position.set(-10, 4, -12);
    scene.add(rim);

    const { root, partGroups, wiring } = buildGlasses();
    scene.add(root);

    // Frame the camera from the model's own measured size rather than from
    // hand-picked coordinates. The device is deeper (temple to temple tip)
    // than it is wide, so a distance guessed from the 14cm frame width leaves
    // the rear-mounted speaker and motor outside the view entirely.
    //
    // Measured with the exploded offsets applied, not assembled. Fitting to
    // the assembled model and padding by a guessed margin is what the first
    // two attempts did, and both clipped: the exploded model is a 15.07 unit
    // radius against 11.12 assembled, so it needs 1.355x — more than either
    // guess. Measuring the state that actually has to fit removes the guess,
    // and keeps working if a part's explode offset is retuned later.
    const measureExplode = (sign) => {
      for (const part of PARTS) {
        const group = partGroups[part.id];
        group.position.addScaledVector(group.userData.explode, sign);
      }
    };
    measureExplode(1);
    const radius = new THREE.Box3().setFromObject(root).getBoundingSphere(new THREE.Sphere()).radius;
    measureExplode(-1);

    const fitDistance = (radius / Math.sin((camera.fov * Math.PI) / 360)) * 1.05;
    HOME_POSITION.set(0.55, 0.42, 1).normalize().multiplyScalar(fitDistance);
    camera.position.copy(HOME_POSITION);
    controls.minDistance = fitDistance * 0.35;
    controls.maxDistance = fitDistance * 3;

    // Assembled positions, captured once so the exploded view can interpolate
    // from them instead of accumulating drift frame over frame.
    const homePositions = {};
    for (const part of PARTS) {
      homePositions[part.id] = partGroups[part.id].position.clone();
    }

    // --- Selection highlight -------------------------------------------
    // Every material here was created fresh in glassesModel.js, so mutating
    // emissive is safe: no two parts share a material instance.
    // Each material's own resting opacity is captured up front. Dimming
    // multiplies that base rather than assigning a flat value, because the
    // lenses rest at 0.16 — assigning the dim value directly would make the
    // glass *more* opaque whenever something else was selected.
    const materialsByPart = {};
    for (const part of PARTS) {
      const list = [];
      partGroups[part.id].traverse((obj) => {
        if (obj.material) {
          obj.material.userData.baseOpacity = obj.material.opacity;
          list.push(obj.material);
        }
      });
      materialsByPart[part.id] = list;
    }

    let appliedSelection = undefined;
    function applySelection(id) {
      if (appliedSelection === id) return;
      appliedSelection = id;
      for (const part of PARTS) {
        const isSelected = part.id === id;
        for (const material of materialsByPart[part.id]) {
          material.emissive.set(isSelected ? 0x2a3550 : 0x000000);
          // Fade everything else back so the selected part reads clearly even
          // when it sits behind another component.
          const base = material.userData.baseOpacity;
          material.opacity = id && !isSelected ? base * 0.4 : base;
          material.transparent = material.opacity < 1;
        }
      }
    }

    // --- Picking --------------------------------------------------------
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let downAt = null;

    function onPointerDown(event) {
      downAt = { x: event.clientX, y: event.clientY };
    }

    function onPointerUp(event) {
      // Orbiting ends in a pointerup too. Without this, every drag to rotate
      // the model would also fire a selection on whatever ended up under the
      // cursor.
      if (!downAt) return;
      const moved = Math.hypot(event.clientX - downAt.x, event.clientY - downAt.y);
      downAt = null;
      if (moved > 6) return;

      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);

      const hits = raycaster.intersectObject(root, true);
      const hit = hits.find((h) => h.object.userData.partId);
      onSelect(hit ? hit.object.userData.partId : null);
    }

    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointerup", onPointerUp);

    // --- Sizing ---------------------------------------------------------
    function resize() {
      const width = mount.clientWidth;
      const height = mount.clientHeight;
      if (width === 0 || height === 0) return;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    }
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(mount);

    // --- Render loop ----------------------------------------------------
    // The explode value is eased toward its target rather than applied
    // directly, so dragging the slider produces motion instead of teleporting
    // parts, and clicking a preset animates.
    let easedExplode = explode;
    const offset = new THREE.Vector3();

    function tick() {
      if (disposed) return;
      const { explode: target, selectedId: wantSelected, autoRotate: spin } = inputs.current;

      easedExplode += (target - easedExplode) * 0.12;

      for (const part of PARTS) {
        const group = partGroups[part.id];
        offset.copy(group.userData.explode).multiplyScalar(easedExplode);
        group.position.copy(homePositions[part.id]).add(offset);
      }

      // Wiring only makes sense on an assembled device; stretched across an
      // exploded view it hides the components it exists to explain.
      const wiringOpacity = Math.max(0, 1 - easedExplode * 2.2);
      wiring.visible = wiringOpacity > 0.02;
      wiring.traverse((obj) => {
        if (obj.material) obj.material.opacity = wiringOpacity;
      });

      applySelection(wantSelected);

      controls.autoRotate = spin;
      controls.update();
      renderer.render(scene, camera);
      frameId = requestAnimationFrame(tick);
    }
    tick();

    return () => {
      disposed = true;
      if (frameId) cancelAnimationFrame(frameId);
      observer.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      controls.dispose();
      disposeGlasses(root);
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) {
        mount.removeChild(renderer.domElement);
      }
      resetRef.current = null;
    };
    // Built once. Live values reach the loop through `inputs`, and camera
    // resets through `resetRef` — neither should tear down the WebGL context.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (resetSignal > 0) resetRef.current?.();
  }, [resetSignal]);

  return <div ref={mountRef} className="glasses-scene" />;
}
