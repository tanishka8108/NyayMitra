import type { UploadExplainResult } from "../../api/courtOrderApi";

type Props = { document: UploadExplainResult };

export default function CourtOrderDetails({ document }: Props) {
  return (
    <section className="juris-document-details">
      <h3>Document details</h3>

      <div className="juris-document-meta">
        <span>Pages: {document.metadata.page_count}</span>
        <span>Sections found: {document.metadata.sections_found}</span>
        <span>
          OCR used: {document.metadata.ocr_used ? "Yes" : "No"}
        </span>
      </div>

      {document.layers && (
        <div className="juris-document-layers">
          {document.layers.legal && (
            <details>
              <summary>Original legal wording</summary>
              <p>{document.layers.legal}</p>
            </details>
          )}
          {document.layers.simple && (
            <details open>
              <summary>Simple English</summary>
              <p>{document.layers.simple}</p>
            </details>
          )}
          {document.layers.translated && (
            <details>
              <summary>Translated explanation</summary>
              <p>{document.layers.translated}</p>
            </details>
          )}
        </div>
      )}

      {document.sections?.length > 0 && (
        <div className="juris-document-sections">
          <h3>Order sections</h3>
          {document.sections.map((section) => (
            <details key={section.section_id}>
              <summary>
                {section.title}
                {!section.available ? " — Not found in document" : ""}
              </summary>
              {section.available && (
                <>
                  {section.simple_text && <p>{section.simple_text}</p>}
                  {!section.simple_text && section.text && (
                    <p>{section.text}</p>
                  )}
                  {section.page_start != null && (
                    <small>
                      Page {section.page_start}
                      {section.page_end != null &&
                      section.page_end !== section.page_start
                        ? `–${section.page_end}`
                        : ""}
                    </small>
                  )}
                </>
              )}
              {section.note && <p>{section.note}</p>}
            </details>
          ))}
        </div>
      )}
    </section>
  );
}
