import { FormEvent, useState } from "react";
import { PlanInput } from "../api";

interface Props {
  loading: boolean;
  onSubmit: (input: PlanInput) => void;
}

function defaultDeparture(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(8, 0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function TripForm({ loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [departure, setDeparture] = useState(defaultDeparture);
  const [loadWeight, setLoadWeight] = useState("30000");
  const [interval, setInterval] = useState("25");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit({
      origin: origin.trim(),
      destination: destination.trim(),
      departure: new Date(departure).toISOString(),
      load_weight: Number(loadWeight),
      interval: Number(interval),
    });
  }

  return (
    <form className="trip-form" onSubmit={handleSubmit}>
      <label>
        Origin
        <input
          value={origin}
          onChange={(e) => setOrigin(e.target.value)}
          placeholder="Chicago, IL"
          required
        />
      </label>
      <label>
        Destination
        <input
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          placeholder="Denver, CO"
          required
        />
      </label>
      <label>
        Departure
        <input
          type="datetime-local"
          value={departure}
          onChange={(e) => setDeparture(e.target.value)}
          required
        />
      </label>
      <div className="form-row">
        <label>
          Load weight (lb)
          <input
            type="number"
            min="0"
            step="500"
            value={loadWeight}
            onChange={(e) => setLoadWeight(e.target.value)}
            required
          />
        </label>
        <label>
          Checkpoints every
          <select value={interval} onChange={(e) => setInterval(e.target.value)}>
            <option value="10">10 mi</option>
            <option value="25">25 mi</option>
            <option value="50">50 mi</option>
          </select>
        </label>
      </div>
      <button type="submit" disabled={loading}>
        {loading && <span className="spinner" />}
        {loading ? "Planning route" : "Find routes"}
      </button>
    </form>
  );
}
