import { useState } from "react";

import type { CustomComponentProps } from "~/components";

type JsonSchema = Record<string, any>;

type ToolSpec = {
  slug?: string;
  name?: string;
  description?: string;
  version?: string;
  input_parameters?: JsonSchema;
  output_parameters?: JsonSchema;
  toolkit?: { slug?: string; name?: string; logo?: string };
  deprecated?: { is_deprecated?: boolean; version?: string };
  no_auth?: boolean;
  tags?: string[];
};

const DESCRIPTION_CLAMP_CHARS = 280;

export function ToolPage({ tool }: CustomComponentProps & { tool: ToolSpec }) {
  const sections: Array<{ id: string; label: string; schema?: JsonSchema }> = [
    { id: "input", label: "Input", schema: tool.input_parameters },
    { id: "output", label: "Output", schema: tool.output_parameters },
  ].filter((section) => hasProperties(section.schema));

  const [activeSectionId, setActiveSectionId] = useState(
    sections[0]?.id ?? "input"
  );
  const [view, setView] = useState<"schema" | "json">("schema");

  const activeSection =
    sections.find((section) => section.id === activeSectionId) ?? sections[0];

  return (
    <div className="container-lg my-4" style={{ maxWidth: "760px" }}>
      <ToolHeader tool={tool} />
      <ToolMeta tool={tool} />
      <ToolDescription description={tool.description} />

      {activeSection && (
        <div className="mt-4">
          <div className="d-flex align-items-center justify-content-between border-bottom">
            <div className="d-flex gap-3">
              {sections.map((section) => (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => setActiveSectionId(section.id)}
                  className={
                    "btn border-0 rounded-0 px-1 pb-2 fw-bold " +
                    (section.id === activeSection.id
                      ? "border-bottom border-2 border-dark text-dark"
                      : "text-muted")
                  }
                >
                  {section.label}
                </button>
              ))}
            </div>
            <div className="btn-group btn-group-sm mb-1" role="group">
              <button
                type="button"
                onClick={() => setView("schema")}
                className={
                  "btn " +
                  (view === "schema" ? "btn-dark" : "btn-outline-secondary")
                }
              >
                Schema
              </button>
              <button
                type="button"
                onClick={() => setView("json")}
                className={
                  "btn " +
                  (view === "json" ? "btn-dark" : "btn-outline-secondary")
                }
              >
                JSON
              </button>
            </div>
          </div>

          {view === "schema" ? (
            <SchemaFields schema={activeSection.schema!} />
          ) : (
            <pre
              className="bg-light rounded-3 p-3 mt-3 small overflow-auto"
              style={{ maxHeight: "60vh" }}
            >
              {JSON.stringify(activeSection.schema, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function ToolHeader({ tool }: { tool: ToolSpec }) {
  const isDeprecated = tool.deprecated?.is_deprecated;
  return (
    <div className="d-flex align-items-center gap-3">
      {tool.toolkit?.logo && (
        <img
          src={tool.toolkit.logo}
          alt={tool.toolkit.name || tool.toolkit.slug}
          width={32}
          height={32}
          className="rounded"
        />
      )}
      <h1 className="fs-3 fw-bold my-0">
        {tool.name || tool.slug}
        {isDeprecated && " (deprecated)"}
      </h1>
      <span className="badge rounded-pill border text-muted bg-transparent">
        TOOL
      </span>
    </div>
  );
}

function ToolMeta({ tool }: { tool: ToolSpec }) {
  return (
    <div className="mt-3">
      <MetaRow label="Slug">
        <code className="text-dark fw-bold">{tool.slug}</code>
      </MetaRow>
      {tool.version && (
        <MetaRow label="Version">
          <code className="text-dark">{tool.version}</code>
        </MetaRow>
      )}
      {tool.toolkit?.name && (
        <MetaRow label="Toolkit">
          <span>{tool.toolkit.name}</span>
        </MetaRow>
      )}
    </div>
  );
}

function MetaRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="d-flex py-1">
      <div className="text-muted" style={{ width: "100px" }}>
        {label}
      </div>
      <div>{children}</div>
    </div>
  );
}

function ToolDescription({ description }: { description?: string }) {
  const [expanded, setExpanded] = useState(false);
  if (!description) return null;

  const needsClamp = description.length > DESCRIPTION_CLAMP_CHARS;
  let body = description;
  if (needsClamp && !expanded) {
    body = description.slice(0, DESCRIPTION_CLAMP_CHARS).trimEnd() + "…";
  }

  return (
    <div className="mt-3 text-secondary" style={{ whiteSpace: "pre-line" }}>
      {body}
      {needsClamp && (
        <div>
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="btn btn-link border-0 p-0 text-dark text-decoration-underline"
          >
            {expanded ? "Show less" : "Show more"}
          </button>
        </div>
      )}
    </div>
  );
}

function SchemaFields({ schema }: { schema: JsonSchema }) {
  const properties: JsonSchema = schema.properties || {};
  const required: string[] = schema.required || [];

  return (
    <div>
      {Object.entries(properties).map(([name, fieldSchema]) => (
        <SchemaField
          key={name}
          name={name}
          schema={fieldSchema}
          required={required.includes(name)}
        />
      ))}
    </div>
  );
}

function SchemaField({
  name,
  schema,
  required,
}: {
  name: string;
  schema: JsonSchema;
  required: boolean;
}) {
  const nested = getNestedSchema(schema);
  return (
    <div className="py-3 border-bottom">
      <div className="d-flex align-items-center justify-content-between gap-2">
        <div className="d-flex align-items-baseline gap-2">
          <code className="text-dark fw-bold">{name}</code>
          {required && <span className="small text-danger">required</span>}
        </div>
        <span className="badge rounded-pill border text-muted bg-transparent">
          {schemaTypeLabel(schema)}
        </span>
      </div>
      {schema.description && (
        <div className="text-secondary mt-1">{schema.description}</div>
      )}
      {schema.enum && (
        <div className="mt-1 small text-muted">
          Options:{" "}
          {schema.enum.map((option: any, i: number) => (
            <span key={String(option)}>
              {i > 0 && ", "}
              <code>{String(option)}</code>
            </span>
          ))}
        </div>
      )}
      {schema.default !== undefined && (
        <div className="mt-1 small text-muted">
          Default: <code>{JSON.stringify(schema.default)}</code>
        </div>
      )}
      {nested && hasProperties(nested) && (
        <div className="ms-3 mt-2 ps-3 border-start">
          <SchemaFields schema={nested} />
        </div>
      )}
    </div>
  );
}

function getNestedSchema(schema: JsonSchema): JsonSchema | null {
  if (schema.type === "object" && schema.properties) {
    return schema;
  }
  if (schema.type === "array" && schema.items?.properties) {
    return schema.items;
  }
  return null;
}

function schemaTypeLabel(schema: JsonSchema): string {
  let type = schema.type;
  if (!type && schema.anyOf) {
    type = schema.anyOf
      .map((sub: JsonSchema) => sub.type)
      .filter(Boolean)
      .join(" | ");
  }
  if (type === "array") {
    const itemType = schema.items?.type;
    if (itemType) {
      return `ARRAY<${String(itemType).toUpperCase()}>`;
    }
  }
  if (!type) return "OBJECT";
  return String(type).toUpperCase();
}

function hasProperties(schema?: JsonSchema): boolean {
  return Boolean(schema && Object.keys(schema.properties || {}).length);
}
