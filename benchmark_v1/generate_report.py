from __future__ import annotations

import html
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "benchmark.sqlite"
OUT_PATH = ROOT / "report.html"


CSS = """
:root {
  color-scheme: dark;
}
body {
  font-family: Inter, system-ui, sans-serif;
  margin: 24px;
  background: #0f1115;
  color: #ecf0f6;
}
h1, h2, h3 {
  margin-top: 0;
}
.summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.card, .question-card {
  background: #171a21;
  border: 1px solid #2a3140;
  border-radius: 12px;
  padding: 16px;
}
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 20px 0;
  align-items: center;
}
input, select {
  background: #0f1115;
  color: #ecf0f6;
  border: 1px solid #394356;
  border-radius: 8px;
  padding: 8px 10px;
}
.question-card {
  margin: 16px 0;
}
.meta {
  color: #b7c0cf;
  font-size: 14px;
  margin-bottom: 8px;
}
.responses {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 12px;
}
.response {
  background: #11141b;
  border: 1px solid #2a3140;
  border-radius: 10px;
  padding: 12px;
}
.model {
  font-weight: 700;
  margin-bottom: 4px;
}
.status {
  font-size: 12px;
  color: #b7c0cf;
  margin-bottom: 8px;
}
pre {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, monospace;
  font-size: 13px;
  margin: 0;
}
.small {
  color: #b7c0cf;
  font-size: 13px;
}
.hidden {
  display: none;
}
"""


JS = """
const subsetFilter = document.getElementById('subsetFilter');
const scoreFilter = document.getElementById('scoreFilter');
const questionCards = [...document.querySelectorAll('.question-card')];

function applyFilters() {
  const subset = subsetFilter.value;
  const minScore = parseFloat(scoreFilter.value || '0');

  questionCards.forEach(card => {
    const cardSubset = card.dataset.subset;
    const cardScore = parseFloat(card.dataset.score || '0');
    const show = (subset === 'all' || subset === cardSubset) && cardScore >= minScore;
    card.classList.toggle('hidden', !show);
  });
}

subsetFilter.addEventListener('change', applyFilters);
scoreFilter.addEventListener('input', applyFilters);
applyFilters();
"""


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        run_row = conn.execute("SELECT id, run_name, created_at FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        if not run_row:
            raise SystemExit("No runs found. Run benchmark_v1/run_benchmark.py first.")
        run_id = int(run_row["id"])

        rows = conn.execute(
            """
            SELECT
              q.id AS question_id,
              q.subset,
              q.question_text,
              COALESCE(qm.divergence_score, 0) AS divergence_score,
              COALESCE(qm.refusal_rate, 0) AS refusal_rate,
              COALESCE(qm.lexical_divergence, 0) AS lexical_divergence,
              COALESCE(qm.stance_divergence, 0) AS stance_divergence,
              COALESCE(qm.self_report_divergence, 0) AS self_report_divergence,
              COALESCE(qm.refusal_divergence, 0) AS refusal_divergence,
              COALESCE(qm.length_divergence, 0) AS length_divergence,
              qm.notes AS notes,
              m.provider,
              m.model_name,
              r.raw_answer,
              r.refused,
              r.error,
              r.error_message
            FROM questions q
            LEFT JOIN question_metrics qm
              ON q.id = qm.question_id AND qm.run_id = ?
            LEFT JOIN responses r
              ON q.id = r.question_id AND r.run_id = ?
            LEFT JOIN models m
              ON r.model_id = m.id
            WHERE q.active = 1
            ORDER BY divergence_score DESC, q.id, m.provider, m.model_name
            """,
            (run_id, run_id),
        ).fetchall()

        grouped: dict[int, dict] = {}
        subsets: set[str] = set()
        model_labels: set[str] = set()
        for row in rows:
            qid = int(row["question_id"])
            subsets.add(str(row["subset"]))
            grouped.setdefault(
                qid,
                {
                    "subset": str(row["subset"]),
                    "question_text": str(row["question_text"]),
                    "divergence_score": float(row["divergence_score"] or 0),
                    "refusal_rate": float(row["refusal_rate"] or 0),
                    "lexical_divergence": float(row["lexical_divergence"] or 0),
                    "stance_divergence": float(row["stance_divergence"] or 0),
                    "self_report_divergence": float(row["self_report_divergence"] or 0),
                    "refusal_divergence": float(row["refusal_divergence"] or 0),
                    "length_divergence": float(row["length_divergence"] or 0),
                    "notes": row["notes"] or "",
                    "responses": [],
                },
            )
            if row["provider"] is not None:
                label = f"{row['provider']} / {row['model_name']}"
                model_labels.add(label)
                grouped[qid]["responses"].append(
                    {
                        "label": label,
                        "raw_answer": row["raw_answer"] or "",
                        "refused": int(row["refused"] or 0),
                        "error": int(row["error"] or 0),
                        "error_message": row["error_message"] or "",
                    }
                )

        leaderboard = sorted(grouped.items(), key=lambda item: item[1]["divergence_score"], reverse=True)[:10]

        summary_html = f"""
        <div class=\"summary\">
          <div class=\"card\"><h3>Run</h3><div>{html.escape(str(run_row['run_name']))}</div><div class=\"small\">id {run_id}</div></div>
          <div class=\"card\"><h3>Questions</h3><div>{len(grouped)}</div></div>
          <div class=\"card\"><h3>Models</h3><div>{len(model_labels)}</div></div>
          <div class=\"card\"><h3>Generated</h3><div>{html.escape(str(run_row['created_at']))}</div></div>
        </div>
        """

        leaderboard_html = "".join(
            f"<li>q{qid} · {html.escape(data['subset'])} · score {data['divergence_score']:.3f} — {html.escape(data['question_text'])}</li>"
            for qid, data in leaderboard
        )

        question_cards = []
        for qid, data in sorted(grouped.items(), key=lambda item: item[1]["divergence_score"], reverse=True):
            response_html = []
            for response in data["responses"]:
                status_parts = []
                if response["refused"]:
                    status_parts.append("REFUSED")
                if response["error"]:
                    status_parts.append("ERROR")
                status_text = " · ".join(status_parts) if status_parts else "OK"
                body = response["raw_answer"] or response["error_message"] or ""
                response_html.append(
                    f"""
                    <div class=\"response\">
                      <div class=\"model\">{html.escape(response['label'])}</div>
                      <div class=\"status\">{html.escape(status_text)}</div>
                      <pre>{html.escape(body)}</pre>
                    </div>
                    """
                )

            question_cards.append(
                f"""
                <section class=\"question-card\" data-subset=\"{html.escape(data['subset'])}\" data-score=\"{data['divergence_score']:.4f}\">
                  <div class=\"meta\">q{qid} · {html.escape(data['subset'])} · divergence {data['divergence_score']:.3f} · refusal {data['refusal_rate']:.2f}{(' · indicator ' + html.escape(data['notes'])) if data['notes'] else ''}</div>
                  <div class=\"small\">components → lexical {data['lexical_divergence']:.3f} · stance {data['stance_divergence']:.3f} · self-report {data['self_report_divergence']:.3f} · refusal {data['refusal_divergence']:.3f} · length {data['length_divergence']:.3f}</div>
                  <h2>{html.escape(data['question_text'])}</h2>
                  <div class=\"responses\">{''.join(response_html)}</div>
                </section>
                """
            )

        filter_options = "".join(
            f"<option value=\"{html.escape(subset)}\">{html.escape(subset)}</option>"
            for subset in sorted(subsets)
        )

        html_doc = f"""
        <!doctype html>
        <html>
        <head>
          <meta charset=\"utf-8\" />
          <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
          <title>LLM Divergence Report</title>
          <style>{CSS}</style>
        </head>
        <body>
          <h1>LLM Divergence Report</h1>
          {summary_html}
          <div class=\"card\">
            <h3>Top divergent questions</h3>
            <ol>{leaderboard_html}</ol>
          </div>
          <div class=\"controls\">
            <label>Subset
              <select id=\"subsetFilter\">
                <option value=\"all\">all</option>
                {filter_options}
              </select>
            </label>
            <label>Min divergence
              <input id=\"scoreFilter\" type=\"number\" step=\"0.01\" min=\"0\" max=\"1\" value=\"0\" />
            </label>
          </div>
          {''.join(question_cards)}
          <script>{JS}</script>
        </body>
        </html>
        """

        OUT_PATH.write_text(html_doc, encoding="utf-8")
        print(f"Wrote {OUT_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
