/** Procedural 3D model of the VoxMind Glasses, built from primitives rather
 * than loaded from a downloaded GLTF.
 *
 * Two reasons it is built in code:
 *   1. It is our own design. A model asset pulled off a stock site could not
 *      honestly be presented as the project's industrial design in a report.
 *   2. Every component has to be individually addressable — selectable,
 *      labelled, and separable in an exploded view. That is far easier when
 *      each part is a named group we constructed than when it is one baked
 *      mesh from an exporter.
 *
 * Units are centimetres, roughly life-size: the frame is ~14cm across, which
 * is a real adult eyewear width. Component sizes follow the actual bill of
 * materials (see tasks/phase2-plan.md §7) — the XIAO ESP32S3 Sense really is
 * 21 x 17.5mm, and it is modelled at 2.1 x 1.75 units here.
 *
 * Component colours are deliberately NOT realistic. On the real board almost
 * everything is black PCB and would read as one dark smudge. This is a
 * teaching diagram, so each part gets a distinct hue that the legend in the
 * parts panel maps back to a name.
 */

import * as THREE from "three";

/** Every part of the device, in the order the parts panel lists them.
 *
 * `explode` is the direction and distance the part travels in the exploded
 * view, as a plain [x, y, z] offset from its assembled position. They are
 * hand-tuned rather than computed radially: a naive "push everything away
 * from the centre" sends the two temple-mounted boards through each other,
 * because they start at nearly the same radius.
 */
export const PARTS = [
  {
    id: "frame",
    name: "Frame and temples",
    color: "#2f333a",
    price: null,
    role: "The body everything mounts to.",
    detail:
      "3D-printed or acetate eyewear frame. The electronics are distributed across both temples so the weight sits over the ears rather than on the nose.",
    explode: [0.0, 0.0, 0.0],
  },
  {
    id: "lenses",
    name: "Lenses",
    color: "#9fd3ff",
    price: null,
    role: "Plain or prescription glass.",
    detail:
      "Non-functional to the electronics. They matter socially: the device has to look like ordinary glasses, not like medical equipment, or people will not wear it.",
    explode: [0.0, 0.0, 1.86],
  },
  {
    id: "xiao",
    name: "Seeed XIAO ESP32S3 Sense",
    color: "#4f46e5",
    price: 1900,
    role: "The brain. WiFi, camera interface and microphone on one thumbnail-sized board.",
    detail:
      "Chosen over the cheaper ESP32-CAM specifically because it carries a microphone. Without a microphone the user cannot ask a question, and the device stops being an assistant.",
    explode: [3.41, 0.93, 0.0],
  },
  {
    id: "camera",
    name: "Camera module",
    color: "#0ea5e9",
    price: null,
    role: "Sees what is in front of the wearer.",
    detail:
      "Rides on the XIAO's ribbon cable but is mounted at the front corner of the frame, so it points where the head points. Only captures when the button is pressed — it does not film continuously.",
    explode: [1.55, 1.55, 1.86],
  },
  {
    id: "distance",
    name: "VL53L1X distance sensor",
    color: "#f59e0b",
    price: 450,
    role: "Instant obstacle detection, out to 4 metres. Works with no internet.",
    detail:
      "A time-of-flight laser sensor on the bridge, facing forward. This is the safety layer: it never waits for the network, an AI model, or a server. Under 2.5 metres it fires the vibration motor directly, and buzzes faster as the obstacle closes. Upgraded from the VL53L0X, which tops out at 2 metres and manages closer to 1.2 in daylight — too late to be useful at walking pace, since 2.5 metres is only about two seconds of warning.",
    explode: [0.0, 2.17, 1.86],
  },
  {
    id: "motor",
    name: "Vibration motor",
    color: "#ef4444",
    price: 50,
    role: "The warning the wearer feels.",
    detail:
      "A coin motor against the right temple. Deliberately not a beep: a blind user navigates by sound, so filling their ears with alerts takes away the sense they depend on. A buzz is felt, and leaves hearing free.",
    explode: [3.41, -1.36, -0.62],
  },
  {
    id: "amp",
    name: "MAX98357A amplifier",
    color: "#10b981",
    price: 250,
    role: "Drives the speaker from the board's digital audio.",
    detail:
      "Takes I2S digital audio straight from the XIAO. This is why the server returns raw 16-bit PCM instead of MP3 — the device has no spare cycles to decode audio, so the decoding happens in the cloud.",
    explode: [-3.41, 0.93, 0.0],
  },
  {
    id: "speaker",
    name: "Speaker, 3W 4Ω",
    color: "#8b5cf6",
    price: 100,
    role: "Speaks the answer.",
    detail:
      "Mounted at the rear of the left temple, close to the ear and angled inward, so it can stay quiet enough not to broadcast the wearer's private questions to everyone nearby.",
    explode: [-3.41, -1.36, -0.62],
  },
  {
    id: "button",
    name: "Push button",
    color: "#ec4899",
    price: 20,
    role: "Press to ask.",
    detail:
      "One button, findable by touch on the left temple. Press and speak to ask a question; press without speaking and the device just describes what is ahead.",
    explode: [-1.86, 2.17, 0.0],
  },
  {
    id: "power",
    name: "Power tether",
    color: "#64748b",
    price: null,
    role: "USB-C to a pocket power bank.",
    detail:
      "A deliberate prototype-stage choice. Strapping a loose lithium cell to something worn on a person's face, wired by a first-time electronics team, is a burn risk. A tethered power bank is the honest engineering answer at this stage.",
    explode: [1.24, -2.17, -1.86],
  },
];

const FRAME_COLOR = "#2f333a";

// Frame geometry constants, shared by the builders below so a change to the
// lens size does not have to be chased through six separate literals.
const LENS_R = 2.3;
const LENS_X = 3.6;
const RIM_TUBE = 0.18;
const TEMPLE_X = 6.0;
const TEMPLE_Y = 0.85;
const TEMPLE_LEN = 13;
const HINGE_Z = 0;

function matte(color, extra = {}) {
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(color),
    roughness: 0.55,
    metalness: 0.15,
    ...extra,
  });
}

/** Wraps meshes in a group tagged with the part id, so a raycast hit on any
 * child can be walked back up to "which component is this". */
function partGroup(id, meshes) {
  const group = new THREE.Group();
  group.name = id;
  group.userData.partId = id;
  for (const mesh of meshes) {
    mesh.userData.partId = id;
    group.add(mesh);
  }
  return group;
}

function buildFrame() {
  const mat = matte(FRAME_COLOR, { roughness: 0.4 });
  const meshes = [];

  // Lens rims.
  for (const sign of [-1, 1]) {
    const rim = new THREE.Mesh(new THREE.TorusGeometry(LENS_R, RIM_TUBE, 14, 56), mat);
    rim.position.set(sign * LENS_X, 0, 0);
    meshes.push(rim);
  }

  // Bridge across the nose, joining the inner edge of each rim.
  const bridge = new THREE.Mesh(new THREE.BoxGeometry(2 * (LENS_X - LENS_R), 0.3, 0.34), mat);
  bridge.position.set(0, 0.95, 0);
  meshes.push(bridge);

  // Nose pads.
  for (const sign of [-1, 1]) {
    const pad = new THREE.Mesh(new THREE.CapsuleGeometry(0.16, 0.5, 4, 8), mat);
    pad.position.set(sign * 0.7, -0.55, 0.35);
    pad.rotation.set(0.35, 0, sign * 0.3);
    meshes.push(pad);
  }

  // End pieces, then the temples themselves running back toward the ears.
  for (const sign of [-1, 1]) {
    const end = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.38, 0.34), mat);
    end.position.set(sign * (LENS_X + LENS_R - 0.1), TEMPLE_Y, HINGE_Z);
    meshes.push(end);

    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.4, TEMPLE_LEN), mat);
    arm.position.set(sign * TEMPLE_X, TEMPLE_Y, HINGE_Z - TEMPLE_LEN / 2);
    meshes.push(arm);

    // The hook that sits over the ear — angled down and slightly inward.
    const hook = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.34, 2.6), mat);
    hook.position.set(sign * (TEMPLE_X - 0.15), TEMPLE_Y - 0.9, HINGE_Z - TEMPLE_LEN - 0.9);
    hook.rotation.set(0.55, 0, 0);
    meshes.push(hook);
  }

  return partGroup("frame", meshes);
}

function buildLenses() {
  // Physical, not Standard: lenses are the one part where a real transmission
  // model is worth the extra cost, because a flat transparent disc reads as a
  // grey blob instead of glass.
  // Opacity is kept very low on purpose. At anything above roughly 0.2 the
  // lenses stop reading as glass and become solid blue discs that hide the
  // temple-mounted electronics sitting behind them — which defeats the point
  // of the view, since those components are what a reviewer came to look at.
  const glass = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color("#bfe4ff"),
    transmission: 0.95,
    thickness: 0.3,
    roughness: 0.06,
    metalness: 0,
    transparent: true,
    opacity: 0.16,
    depthWrite: false,
    side: THREE.DoubleSide,
  });

  const meshes = [];
  for (const sign of [-1, 1]) {
    const lens = new THREE.Mesh(new THREE.CircleGeometry(LENS_R - 0.02, 48), glass);
    lens.position.set(sign * LENS_X, 0, 0);
    meshes.push(lens);
  }
  return partGroup("lenses", meshes);
}

function buildXiao() {
  const board = new THREE.Mesh(new THREE.BoxGeometry(0.28, 1.75, 2.1), matte("#4f46e5"));
  board.position.set(TEMPLE_X + 0.28, 1.0, -2.9);

  // The RF shield can — the silver rectangle that dominates the real board.
  const shield = new THREE.Mesh(
    new THREE.BoxGeometry(0.1, 1.0, 0.95),
    matte("#c7cbd1", { metalness: 0.75, roughness: 0.3 }),
  );
  shield.position.set(TEMPLE_X + 0.45, 1.0, -3.3);

  const usb = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.32, 0.5), matte("#9aa2ad", { metalness: 0.6 }));
  usb.position.set(TEMPLE_X + 0.28, 1.0, -1.95);

  return partGroup("xiao", [board, shield, usb]);
}

function buildCamera() {
  const housing = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.7, 0.45), matte("#0ea5e9"));
  housing.position.set(LENS_X + LENS_R - 0.35, 1.0, 0.3);

  const barrel = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.3, 20), matte("#0b3a55"));
  barrel.rotation.x = Math.PI / 2;
  barrel.position.set(LENS_X + LENS_R - 0.35, 1.0, 0.58);

  // A tiny bright disc so the lens catches the light and reads as glass.
  const glass = new THREE.Mesh(
    new THREE.CircleGeometry(0.16, 20),
    new THREE.MeshStandardMaterial({ color: new THREE.Color("#8fd8ff"), roughness: 0.05, metalness: 0.9 }),
  );
  glass.position.set(LENS_X + LENS_R - 0.35, 1.0, 0.74);

  return partGroup("camera", [housing, barrel, glass]);
}

function buildDistanceSensor() {
  const board = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.5, 0.22), matte("#f59e0b"));
  board.position.set(0, 0.95, 0.34);

  // The two windows on a VL53L0X: one emits the laser pulse, one receives it.
  const meshes = [board];
  for (const sign of [-1, 1]) {
    const window = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 0.08, 16), matte("#3b2a06"));
    window.rotation.x = Math.PI / 2;
    window.position.set(sign * 0.28, 0.95, 0.47);
    meshes.push(window);
  }
  return partGroup("distance", meshes);
}

function buildMotor() {
  const coin = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.26, 24), matte("#ef4444"));
  coin.rotation.z = Math.PI / 2;
  coin.position.set(TEMPLE_X - 0.28, TEMPLE_Y, -6.4);
  return partGroup("motor", [coin]);
}

function buildAmp() {
  const board = new THREE.Mesh(new THREE.BoxGeometry(0.24, 1.3, 1.5), matte("#10b981"));
  board.position.set(-(TEMPLE_X + 0.26), 1.0, -3.4);
  return partGroup("amp", [board]);
}

function buildSpeaker() {
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.75, 0.75, 0.42, 28), matte("#8b5cf6"));
  body.rotation.z = Math.PI / 2;
  body.position.set(-(TEMPLE_X - 0.3), 0.45, -8.9);

  const cone = new THREE.Mesh(new THREE.CircleGeometry(0.55, 28), matte("#3b2f63"));
  cone.rotation.y = Math.PI / 2;
  cone.position.set(-(TEMPLE_X - 0.52), 0.45, -8.9);

  return partGroup("speaker", [body, cone]);
}

function buildButton() {
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.34, 0.14, 20), matte("#7a2350"));
  base.position.set(-TEMPLE_X, TEMPLE_Y + 0.22, -1.9);

  const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.26, 0.28, 0.18, 20), matte("#ec4899"));
  cap.position.set(-TEMPLE_X, TEMPLE_Y + 0.36, -1.9);

  return partGroup("button", [base, cap]);
}

/** A tube swept along a curve — used for both the power tether and the
 * internal wiring runs. */
function tube(points, radius, color, radialSegments = 8) {
  const curve = new THREE.CatmullRomCurve3(points.map((p) => new THREE.Vector3(...p)));
  return new THREE.Mesh(new THREE.TubeGeometry(curve, 40, radius, radialSegments, false), matte(color));
}

function buildPowerTether() {
  const cable = tube(
    [
      [TEMPLE_X + 0.2, 1.0, -2.0],
      [TEMPLE_X + 0.3, 0.9, -6.0],
      [TEMPLE_X + 0.2, 0.2, -11.0],
      [TEMPLE_X - 0.2, -1.6, -14.5],
      [TEMPLE_X - 0.9, -4.2, -16.0],
    ],
    0.11,
    "#64748b",
  );
  return partGroup("power", [cable]);
}

/** The wiring between components.
 *
 * Not in PARTS and not selectable: these are how the parts connect, not parts
 * in their own right, and a report reviewer clicking a wire expecting a spec
 * sheet would be a dead end. They also fade out as the model explodes — a
 * wire stretched across an exploded view is visual noise that obscures the
 * components it is meant to explain.
 */
function buildWiring() {
  const group = new THREE.Group();
  group.name = "wiring";
  group.userData.isWiring = true;

  const runs = [
    // XIAO to the camera at the front of the frame.
    [
      [TEMPLE_X + 0.1, 1.05, -2.0],
      [TEMPLE_X - 0.1, 1.05, -0.8],
      [LENS_X + LENS_R - 0.3, 1.0, 0.1],
    ],
    // XIAO forward and across the brow to the distance sensor on the bridge.
    [
      [TEMPLE_X + 0.05, 1.25, -2.2],
      [LENS_X + 0.6, 1.55, 0.05],
      [1.0, 1.15, 0.2],
      [0.15, 1.0, 0.28],
    ],
    // XIAO back along the right temple to the vibration motor.
    [
      [TEMPLE_X + 0.1, 0.9, -3.6],
      [TEMPLE_X - 0.05, 0.85, -5.2],
      [TEMPLE_X - 0.2, TEMPLE_Y, -6.2],
    ],
    // XIAO across the brow to the amplifier on the left temple.
    [
      [TEMPLE_X + 0.05, 1.2, -2.6],
      [LENS_X, 1.7, 0.0],
      [0, 1.35, 0.1],
      [-LENS_X, 1.7, 0.0],
      [-(TEMPLE_X + 0.1), 1.3, -3.0],
    ],
    // Amplifier back to the speaker.
    [
      [-(TEMPLE_X + 0.15), 0.85, -4.0],
      [-(TEMPLE_X + 0.05), 0.6, -6.8],
      [-(TEMPLE_X - 0.25), 0.45, -8.5],
    ],
    // Button forward and across to the XIAO.
    [
      [-TEMPLE_X, TEMPLE_Y + 0.2, -2.0],
      [-(TEMPLE_X - 0.05), 1.45, -2.9],
      [-(TEMPLE_X + 0.05), 1.25, -3.2],
    ],
  ];

  for (const run of runs) {
    const wire = tube(run, 0.045, "#8a93a0", 6);
    wire.material.transparent = true;
    group.add(wire);
  }
  return group;
}

/** Builds the whole device.
 *
 * Returns the root group plus direct handles to the per-part groups and the
 * wiring, so the scene component can drive the exploded view without
 * re-traversing the tree every frame.
 */
export function buildGlasses() {
  const root = new THREE.Group();

  const builders = {
    frame: buildFrame,
    lenses: buildLenses,
    xiao: buildXiao,
    camera: buildCamera,
    distance: buildDistanceSensor,
    motor: buildMotor,
    amp: buildAmp,
    speaker: buildSpeaker,
    button: buildButton,
    power: buildPowerTether,
  };

  const partGroups = {};
  for (const part of PARTS) {
    const group = builders[part.id]();
    group.userData.explode = new THREE.Vector3(...part.explode);
    root.add(group);
    partGroups[part.id] = group;
  }

  const wiring = buildWiring();
  root.add(wiring);

  // The model is authored with the frame front at z=0 and the temples running
  // backwards, so its centre of mass sits well behind the origin. Rather than
  // nudging it forward by a hand-guessed amount, every child is shifted by the
  // real bounding-box centre — which keeps orbiting centred on the device no
  // matter how the geometry above is edited later.
  const centre = new THREE.Box3().setFromObject(root).getCenter(new THREE.Vector3());
  for (const child of root.children) {
    child.position.sub(centre);
  }

  return { root, partGroups, wiring };
}

/** Frees every GPU resource this model holds.
 *
 * three.js does not garbage-collect geometries, materials or textures when a
 * mesh leaves the scene graph — they live on the GPU until explicitly
 * disposed. Without this, React's StrictMode double-mount alone leaks a whole
 * duplicate model before the user has touched anything.
 */
export function disposeGlasses(root) {
  root.traverse((obj) => {
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) {
      const materials = Array.isArray(obj.material) ? obj.material : [obj.material];
      for (const material of materials) material.dispose();
    }
  });
}
