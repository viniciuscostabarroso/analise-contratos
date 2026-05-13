import React from "react";

export default function SectionCard({ title, icon, sectionId, children }) {
  return (
    <section id={sectionId} className="section-card">
      <h3 className="section-title">
        <span className="section-icon">{icon}</span> {title}
      </h3>
      {children}
    </section>
  );
}
