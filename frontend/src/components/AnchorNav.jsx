import React from "react";

export default function AnchorNav({ sections }) {
  if (!sections || sections.length === 0) {
    return null;
  }

  return (
    <nav className="anchor-nav" aria-label="Navegacao das secoes do resultado">
      {sections.map((section) => (
        <a key={section.id} className="anchor-link" href={`#${section.id}`}>
          {section.label}
        </a>
      ))}
    </nav>
  );
}
