export default function Visualizer({ active }) {
  return (
    <div className={`visualizer${active ? " active" : ""}`} aria-hidden="true">
      {Array.from({ length: 5 }).map((_, i) => (
        // eslint-disable-next-line react/no-array-index-key
        <span key={i} className="bar" />
      ))}
    </div>
  );
}
