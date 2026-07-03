import { useMemo, useState } from "react";
import { hashCategoryColor, useStore } from "../store";
import type { NodeSpec } from "../types";

export const DRAG_MIME = "application/canvs-node-spec";

export function Palette() {
  const registry = useStore((s) => s.registry);
  const [query, setQuery] = useState("");

  const grouped = useMemo(() => {
    if (!registry) return [];
    const q = query.trim().toLowerCase();
    const filtered = registry.nodes.filter(
      (n) =>
        !q ||
        n.name.toLowerCase().includes(q) ||
        n.id.toLowerCase().includes(q) ||
        n.category.toLowerCase().includes(q)
    );
    const byCategory = new Map<string, NodeSpec[]>();
    for (const n of filtered) {
      const list = byCategory.get(n.category) ?? [];
      list.push(n);
      byCategory.set(n.category, list);
    }
    return [...byCategory.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [registry, query]);

  return (
    <div className="palette">
      <div className="palette-search">
        <input
          type="text"
          placeholder="Search nodes..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <div className="palette-list">
        {!registry && <div className="palette-empty">Loading registry...</div>}
        {registry && grouped.length === 0 && <div className="palette-empty">No nodes found</div>}
        {grouped.map(([category, specs]) => (
          <div className="palette-category" key={category}>
            <div className="palette-category-header" style={{ borderColor: hashCategoryColor(category) }}>
              {category}
            </div>
            {specs.map((spec) => (
              <div
                key={spec.id}
                className="palette-item"
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData(DRAG_MIME, JSON.stringify(spec));
                  e.dataTransfer.effectAllowed = "move";
                }}
                title={spec.description}
              >
                <span
                  className="palette-item-accent"
                  style={{ background: hashCategoryColor(spec.category) }}
                />
                <span className="palette-item-name">{spec.name}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
