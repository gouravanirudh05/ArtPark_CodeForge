import { useState, useRef } from "react";

const API = "http://localhost:8000";

// ─── API client ─────────────────────────────────────────────────────────────

async function runAnalysis(resumeFile, jd, roleTitle) {
  const form = new FormData();
  form.append("resume", resumeFile);
  form.append("job_description", jd);
  form.append("role_title", roleTitle);
  const res = await fetch(`${API}/analyze`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Analysis failed");
  }
  return res.json();
}

// ─── Colour helpers ──────────────────────────────────────────────────────────

const priorityColor = {
  high:   { bg: "#FFF0EE", text: "#7B2A1A", border: "#F0997B" },
  medium: { bg: "#FFFAE6", text: "#6B4A00", border: "#FAC775" },
  low:    { bg: "#EAF3DE", text: "#27500A", border: "#97C459" },
};

const difficultyColor = {
  beginner:     "#1D9E75",
  intermediate: "#BA7517",
  advanced:     "#D85A30",
  expert:       "#993C1D",
};

// ─── Sub-components ──────────────────────────────────────────────────────────

function UploadZone({ onFile, file }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef();

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type === "application/pdf") onFile(f);
  };

  return (
    <div
      onClick={() => inputRef.current.click()}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      style={{
        border: `2px dashed ${dragging ? "#1D9E75" : file ? "#1D9E75" : "#B4B2A9"}`,
        borderRadius: 12,
        padding: "2rem",
        textAlign: "center",
        cursor: "pointer",
        background: file ? "#E1F5EE" : dragging ? "#F0FFF8" : "#FAFAF8",
        transition: "all 0.2s",
      }}
    >
      <input ref={inputRef} type="file" accept=".pdf" style={{ display: "none" }}
        onChange={(e) => onFile(e.target.files[0])} />
      <div style={{ fontSize: 28, marginBottom: 8 }}>📄</div>
      {file
        ? <p style={{ color: "#0F6E56", fontWeight: 500 }}>{file.name}</p>
        : <p style={{ color: "#888780" }}>Drop resume PDF here or click to browse</p>
      }
    </div>
  );
}

function SkillBadge({ skill }) {
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 10px",
      borderRadius: 99,
      fontSize: 12,
      fontWeight: 500,
      background: "#EEEDFE",
      color: "#3C3489",
      border: "1px solid #AFA9EC",
      margin: "2px 3px",
    }}>
      {skill.name}
      {skill.proficiency && (
        <span style={{ opacity: 0.65, marginLeft: 4 }}>· {skill.proficiency}</span>
      )}
    </span>
  );
}

function GapBar({ gap }) {
  const col = priorityColor[gap.priority] || priorityColor.low;
  return (
    <div style={{
      padding: "10px 14px",
      borderRadius: 10,
      background: col.bg,
      border: `1px solid ${col.border}`,
      marginBottom: 8,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontWeight: 500, color: col.text, fontSize: 14 }}>{gap.skill_name}</span>
        <span style={{
          fontSize: 11, fontWeight: 600, padding: "1px 8px", borderRadius: 99,
          background: col.border, color: col.text, textTransform: "uppercase",
        }}>{gap.priority}</span>
      </div>
      <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{
          flex: 1, height: 6, borderRadius: 99,
          background: "#E0DDD8", overflow: "hidden",
        }}>
          <div style={{
            width: `${gap.gap_score * 100}%`,
            height: "100%",
            borderRadius: 99,
            background: col.border,
            transition: "width 0.6s ease",
          }} />
        </div>
        <span style={{ fontSize: 11, color: col.text, minWidth: 36 }}>
          {Math.round(gap.gap_score * 100)}%
        </span>
      </div>
      <div style={{ fontSize: 11, color: col.text, opacity: 0.8, marginTop: 4 }}>
        Required: <b>{gap.required_proficiency}</b>
        {gap.candidate_proficiency && <> · Has: <b>{gap.candidate_proficiency}</b></>}
      </div>
    </div>
  );
}

function CourseCard({ step, total }) {
  const [open, setOpen] = useState(false);
  const dc = difficultyColor[step.course.difficulty] || "#888";
  return (
    <div style={{
      display: "flex", gap: 16, marginBottom: 0,
    }}>
      {/* Timeline spine */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 32 }}>
        <div style={{
          width: 32, height: 32, borderRadius: "50%",
          background: "#EEEDFE", border: "2px solid #7F77DD",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontWeight: 700, fontSize: 13, color: "#3C3489", flexShrink: 0,
        }}>{step.order}</div>
        {step.order < total && (
          <div style={{ width: 2, flex: 1, minHeight: 24, background: "#D3D1C7", marginTop: 4 }} />
        )}
      </div>

      {/* Card */}
      <div style={{
        flex: 1, border: "1px solid #D3D1C7", borderRadius: 12,
        padding: "14px 16px", marginBottom: 16,
        background: "#FAFAF8", cursor: "pointer",
      }} onClick={() => setOpen(!open)}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 15, color: "#2C2C2A" }}>
              {step.course.title}
            </div>
            <div style={{ fontSize: 12, color: "#888780", marginTop: 2 }}>
              {step.course.provider} · {step.course.duration_hours}h
              <span style={{
                marginLeft: 8, fontWeight: 600,
                color: dc,
                textTransform: "capitalize",
              }}>{step.course.difficulty}</span>
            </div>
          </div>
          <span style={{ fontSize: 18, color: "#B4B2A9" }}>{open ? "▲" : "▼"}</span>
        </div>

        <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 4 }}>
          {step.addresses_gaps.map(g => (
            <span key={g} style={{
              fontSize: 11, padding: "1px 8px", borderRadius: 99,
              background: "#E1F5EE", color: "#0F6E56", border: "1px solid #5DCAA5",
            }}>↑ {g}</span>
          ))}
        </div>

        {open && (
          <div style={{ marginTop: 12, borderTop: "1px solid #E8E6E0", paddingTop: 10 }}>
            <p style={{ fontSize: 13, color: "#5F5E5A", lineHeight: 1.6 }}>
              {step.course.description}
            </p>
            <p style={{ fontSize: 12, color: "#888780", marginTop: 8, fontStyle: "italic" }}>
              Why this step: {step.rationale}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function TracePanel({ traces }) {
  const [open, setOpen] = useState(false);
  const all = [...(traces.extract || []), ...(traces.gap || []), ...(traces.pathway || [])];
  return (
    <div style={{ marginTop: 24, border: "1px solid #D3D1C7", borderRadius: 12, overflow: "hidden" }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          width: "100%", padding: "12px 16px", display: "flex",
          justifyContent: "space-between", alignItems: "center",
          background: "#F1EFE8", border: "none", cursor: "pointer",
          fontSize: 14, fontWeight: 500, color: "#444441",
        }}>
        <span>🔍 Reasoning trace ({all.length} steps)</span>
        <span>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div style={{ padding: 16, background: "#FAFAF8" }}>
          {all.map((step, i) => (
            <div key={i} style={{
              fontSize: 12, fontFamily: "monospace",
              color: "#5F5E5A", padding: "3px 0",
              borderBottom: "1px solid #F1EFE8",
            }}>{step}</div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main App ────────────────────────────────────────────────────────────────

export default function App() {
  const [resumeFile, setResumeFile] = useState(null);
  const [jd, setJd] = useState("");
  const [roleTitle, setRoleTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [tab, setTab] = useState("pathway");

  const canSubmit = resumeFile && jd.trim().length > 20 && !loading;

  const handleSubmit = async () => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await runAnalysis(resumeFile, jd, roleTitle);
      setResult(data);
      setTab("pathway");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const tabs = ["pathway", "gaps", "skills", "trace"];

  return (
    <div style={{
      minHeight: "100vh",
      background: "#F5F3EE",
      fontFamily: "'Segoe UI', system-ui, sans-serif",
    }}>
      {/* Header */}
      <div style={{
        background: "#2C2C2A",
        padding: "18px 32px",
        display: "flex", alignItems: "center", gap: 12,
      }}>
        <div style={{
          width: 32, height: 32, borderRadius: 8,
          background: "#1D9E75",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 16,
        }}>🎯</div>
        <div>
          <div style={{ color: "#fff", fontWeight: 600, fontSize: 16 }}>
            Adaptive Onboarding Engine
          </div>
          <div style={{ color: "#888780", fontSize: 12 }}>
            AI-powered personalized learning pathways
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 24px" }}>

        {/* Upload form */}
        {!result && (
          <div style={{
            background: "#fff",
            borderRadius: 16,
            padding: 28,
            boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
          }}>
            <h2 style={{ margin: "0 0 20px", fontSize: 18, color: "#2C2C2A" }}>
              Upload documents
            </h2>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 13, fontWeight: 500, color: "#5F5E5A", display: "block", marginBottom: 6 }}>
                Resume (PDF)
              </label>
              <UploadZone onFile={setResumeFile} file={resumeFile} />
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 13, fontWeight: 500, color: "#5F5E5A", display: "block", marginBottom: 6 }}>
                Role title (optional)
              </label>
              <input
                value={roleTitle}
                onChange={e => setRoleTitle(e.target.value)}
                placeholder="e.g. Senior ML Engineer"
                style={{
                  width: "100%", padding: "10px 14px", borderRadius: 8,
                  border: "1px solid #D3D1C7", fontSize: 14,
                  background: "#FAFAF8", boxSizing: "border-box",
                  outline: "none",
                }}
              />
            </div>

            <div style={{ marginBottom: 24 }}>
              <label style={{ fontSize: 13, fontWeight: 500, color: "#5F5E5A", display: "block", marginBottom: 6 }}>
                Job description *
              </label>
              <textarea
                value={jd}
                onChange={e => setJd(e.target.value)}
                placeholder="Paste the full job description here..."
                rows={8}
                style={{
                  width: "100%", padding: "10px 14px", borderRadius: 8,
                  border: "1px solid #D3D1C7", fontSize: 14,
                  background: "#FAFAF8", boxSizing: "border-box",
                  resize: "vertical", outline: "none", lineHeight: 1.6,
                }}
              />
            </div>

            {error && (
              <div style={{
                padding: "10px 14px", borderRadius: 8, marginBottom: 16,
                background: "#FCEBEB", color: "#501313",
                border: "1px solid #F09595", fontSize: 13,
              }}>{error}</div>
            )}

            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              style={{
                padding: "12px 28px", borderRadius: 10, border: "none",
                background: canSubmit ? "#1D9E75" : "#B4B2A9",
                color: "#fff", fontWeight: 600, fontSize: 15,
                cursor: canSubmit ? "pointer" : "not-allowed",
                transition: "background 0.2s",
              }}>
              {loading ? "Analyzing…" : "Generate learning pathway →"}
            </button>
          </div>
        )}

        {/* Results */}
        {result && (
          <div>
            {/* Summary bar */}
            <div style={{
              display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12,
              marginBottom: 24,
            }}>
              {[
                { label: "Coverage", value: `${result.gap.coverage_percent}%`, color: "#1D9E75" },
                { label: "Skill gaps", value: result.gap.gaps.length, color: "#D85A30" },
                { label: "Learning path", value: `${result.pathway.steps.length} courses`, color: "#534AB7" },
                { label: "Hours saved", value: `${result.pathway.estimated_redundancy_saved_hours}h`, color: "#BA7517" },
              ].map(s => (
                <div key={s.label} style={{
                  background: "#fff", borderRadius: 12, padding: "16px 18px",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
                }}>
                  <div style={{ fontSize: 22, fontWeight: 700, color: s.color }}>{s.value}</div>
                  <div style={{ fontSize: 12, color: "#888780", marginTop: 2 }}>{s.label}</div>
                </div>
              ))}
            </div>

            {/* Tabs */}
            <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
              {tabs.map(t => (
                <button key={t} onClick={() => setTab(t)} style={{
                  padding: "7px 16px", borderRadius: 8, border: "none",
                  background: tab === t ? "#2C2C2A" : "#E8E6E0",
                  color: tab === t ? "#fff" : "#5F5E5A",
                  fontWeight: 500, fontSize: 13, cursor: "pointer",
                  textTransform: "capitalize",
                }}>{t}</button>
              ))}
              <button onClick={() => setResult(null)} style={{
                marginLeft: "auto", padding: "7px 16px", borderRadius: 8,
                border: "1px solid #D3D1C7", background: "transparent",
                color: "#888780", fontSize: 13, cursor: "pointer",
              }}>← New analysis</button>
            </div>

            <div style={{
              background: "#fff", borderRadius: 16, padding: 24,
              boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
            }}>

              {/* Pathway tab */}
              {tab === "pathway" && (
                <div>
                  <h3 style={{ margin: "0 0 6px", fontSize: 16, color: "#2C2C2A" }}>
                    Learning pathway {result.pathway.role_title && `· ${result.pathway.role_title}`}
                  </h3>
                  <p style={{ margin: "0 0 20px", fontSize: 13, color: "#888780" }}>
                    {result.pathway.total_hours}h total ·{" "}
                    {result.pathway.skipped_courses.length} courses skipped (already mastered)
                  </p>
                  {result.pathway.steps.map(step => (
                    <CourseCard key={step.order} step={step} total={result.pathway.steps.length} />
                  ))}
                  {result.pathway.steps.length === 0 && (
                    <p style={{ color: "#888780", textAlign: "center", padding: "32px 0" }}>
                      No courses needed — candidate already meets all requirements!
                    </p>
                  )}
                </div>
              )}

              {/* Gaps tab */}
              {tab === "gaps" && (
                <div>
                  <h3 style={{ margin: "0 0 16px", fontSize: 16, color: "#2C2C2A" }}>
                    Skill gaps ({result.gap.gaps.length})
                  </h3>
                  {result.gap.gaps.sort((a, b) => b.gap_score - a.gap_score).map(g => (
                    <GapBar key={g.skill_name} gap={g} />
                  ))}
                  {result.gap.redundant_skills.length > 0 && (
                    <div style={{ marginTop: 20 }}>
                      <p style={{ fontSize: 13, color: "#888780", marginBottom: 8 }}>
                        Skills not required for this role (can skip training):
                      </p>
                      <div>
                        {result.gap.redundant_skills.map(s => (
                          <span key={s} style={{
                            display: "inline-block", margin: "2px 3px",
                            padding: "2px 10px", borderRadius: 99,
                            background: "#F1EFE8", color: "#5F5E5A",
                            fontSize: 12, border: "1px solid #D3D1C7",
                          }}>{s}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Skills tab */}
              {tab === "skills" && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
                  <div>
                    <h3 style={{ margin: "0 0 12px", fontSize: 15, color: "#2C2C2A" }}>
                      Candidate skills ({result.extract.candidate_skills.length})
                    </h3>
                    <div>
                      {result.extract.candidate_skills.map(s => <SkillBadge key={s.name} skill={s} />)}
                    </div>
                  </div>
                  <div>
                    <h3 style={{ margin: "0 0 12px", fontSize: 15, color: "#2C2C2A" }}>
                      Required skills ({result.extract.required_skills.length})
                    </h3>
                    <div>
                      {result.extract.required_skills.map(s => <SkillBadge key={s.name} skill={s} />)}
                    </div>
                  </div>
                </div>
              )}

              {/* Trace tab */}
              {tab === "trace" && (
                <div>
                  <h3 style={{ margin: "0 0 16px", fontSize: 16, color: "#2C2C2A" }}>
                    Reasoning trace
                  </h3>
                  {[
                    { label: "Skill extraction", steps: result.extract.reasoning_trace },
                    { label: "Gap analysis", steps: result.gap.reasoning_trace },
                    { label: "Path planning", steps: result.pathway.reasoning_trace },
                  ].map(section => (
                    <div key={section.label} style={{ marginBottom: 20 }}>
                      <div style={{
                        fontSize: 12, fontWeight: 600, color: "#534AB7",
                        textTransform: "uppercase", letterSpacing: "0.05em",
                        marginBottom: 8,
                      }}>{section.label}</div>
                      {section.steps.map((step, i) => (
                        <div key={i} style={{
                          fontFamily: "monospace", fontSize: 12,
                          color: "#5F5E5A", padding: "4px 10px",
                          borderLeft: "2px solid #D3D1C7",
                          marginBottom: 3,
                          background: "#FAFAF8",
                          borderRadius: "0 4px 4px 0",
                        }}>{step}</div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
