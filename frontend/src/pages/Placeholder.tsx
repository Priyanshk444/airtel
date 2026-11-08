export default function Placeholder({ title, phase }: { title: string; phase: string }) {
  return (
    <div className="page">
      <div className="card">
        <h2>{title}</h2>
        <p>This screen arrives in {phase}.</p>
      </div>
    </div>
  );
}
