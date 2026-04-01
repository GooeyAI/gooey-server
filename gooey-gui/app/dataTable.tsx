import { useEffect, useState, useMemo } from "react";
import { AgGridReact } from "ag-grid-react";
import {
  ModuleRegistry,
  AllCommunityModule,
  themeQuartz,
} from "ag-grid-community";
import * as XLSX from "xlsx";
import * as cptable from "codepage";
import ReactDOM from "react-dom";

const theme = themeQuartz.withParams({
  borderRadius: 6,
  browserColorScheme: "light",
  fontFamily: "inherit",
  headerFontSize: 14,
  spacing: 4,
  wrapperBorderRadius: 6,
  columnBorder: true,
  headerColumnBorder: true,
  headerFontWeight: 700,
  headerBackgroundColor: "#f7f7f7",
});

XLSX.set_cptable(cptable);

// Register all community modules for AG Grid v34+
ModuleRegistry.registerModules([AllCommunityModule]);

export function DataTable({
  fileUrl,
  cells,
  headerSelect,
  onChange,
  state,
}: {
  fileUrl?: string;
  cells?: Array<any>;
  headerSelect?: Record<string, any>;
  onChange?: (value: any) => void;
  state?: Record<string, any>;
}) {
  const [rowData, setRowData] = useState<Array<any>>([]);
  const [colHeaders, setColHeaders] = useState<Array<string>>([]);
  const [loading, setLoading] = useState<boolean>(!!fileUrl);
  useEffect(() => {
    if (cells && cells.length > 1) {
      let rows = cells.map((row: any) =>
        row.map((cell: any) => {
          if (!cell) {
            cell = { value: "" };
          } else if (typeof cell !== "object") {
            cell = { value: cell };
          }
          cell.value = decodeHTMLEntities(cell.value);
          return cell;
        })
      );
      setColHeaders(rows[0].map((col: any) => col.value));
      setRowData(
        rows
          .slice(1)
          .map((row: any) =>
            Object.fromEntries(
              rows[0].map((col: any, idx: number) => [col.value, row[idx]])
            )
          )
      );
      setLoading(false);
    } else if (fileUrl) {
      (async () => {
        setLoading(true);
        const response = await fetch(fileUrl);
        const data = await response.arrayBuffer();
        const workbook = XLSX.read(data, { codepage: 65001 });
        const sheet = workbook.Sheets[workbook.SheetNames[0]];
        let range = sheet["!ref"]!;
        if (typeof sheet["A1"] === "undefined") {
          range = XLSX.utils.encode_range({
            s: { c: 1, r: 1 },
            e: XLSX.utils.decode_range(range).e,
          });
        }
        // Use the first row as the header for columns
        const allRows: any[][] = XLSX.utils.sheet_to_json(sheet, {
          header: 1,
          range: range,
          raw: false,
        });
        const headerRow: string[] = (allRows[0] || [])
          .filter((colName: any) => colName && !colName.startsWith("__EMPTY"))
          .map(decodeHTMLEntities);
        if (allRows.length > 1 && headerRow.length > 0) {
          setColHeaders(headerRow);
          setRowData(
            allRows
              .slice(1)
              .filter((row: any) => row.length > 0)
              .map((row: any[]) =>
                Object.fromEntries(
                  headerRow.map((col: string, idx: number) => [
                    col,
                    { value: decodeHTMLEntities(row[idx] ?? "") },
                  ])
                )
              )
          );
        }
        setLoading(false);
      })();
    }
  }, [cells, fileUrl]);

  const columnDefs = useMemo(() => {
    let cols = [
      {
        headerName: "",
        field: "__rowNum__",
        valueGetter: (params: any) =>
          params.node ? params.node.rowIndex + 1 : "",
        pinned: "left" as const,
        width: 35,
        suppressMovable: true,
        suppressColumnsToolPanel: true,
        suppressFiltersToolPanel: true,
        suppressAutoSize: true,
        sortable: false,
        filter: false,
        cellStyle: {
          backgroundColor: "#f7f7f7",
          color: "#989898",
        },
      },
      ...colHeaders.map((header) => ({
        field: header,
        headerName: header,
        editable: true,
        cellEditor: "agLargeTextCellEditor",
        cellEditorPopup: true,
        valueGetter: (params: any) => {
          // Always expect an object with a value property
          const cell = params.data?.[header];
          if (cell && typeof cell === "object" && "value" in cell) {
            return cell.value;
          }
          return "";
        },
        cellStyle: (params: any) => {
          const cell = params.data?.[header];
          if (cell && typeof cell === "object" && cell.style) {
            return cell.style;
          }
          return undefined;
        },
      })),
    ];
    return cols;
  }, [colHeaders]);

  if (loading) return <div>Loading...</div>;

  return (
    <FullscreenOverlay>
      <AgGridReact
        theme={theme}
        rowData={rowData}
        autoSizeStrategy={{
          type: "fitCellContents",
          defaultMinWidth: 100,
          columnLimits: [{ colId: "__rowNum__", minWidth: 0 }],
          defaultMaxWidth: 300,
        }}
        readOnlyEdit={true}
        columnDefs={columnDefs}
        defaultColDef={
          headerSelect
            ? {
                headerComponent: HeaderWithSelect,
                headerComponentParams: { headerSelect, onChange, state },
              }
            : {}
        }
      />
    </FullscreenOverlay>
  );
}

function decodeHTMLEntities(text: string) {
  if (typeof text !== "string") return text;
  const txt = document.createElement("textarea");
  txt.innerHTML = text;
  return txt.value;
}

function HeaderWithSelect({
  displayName,
  headerSelect,
  onChange,
  state,
  className = "d-flex align-items-center justify-content-center gap-2 w-100",
}: {
  displayName: string;
  headerSelect: Record<string, any>;
  onChange: (value: any) => void;
  state: Record<string, any>;
  className?: string;
}) {
  if (!displayName) return null;
  let { name, options, ...args } = headerSelect;
  name = name?.replace("{col}", displayName);

  let labelWidget = <span>{displayName}</span>;
  if (!options || options.length === 0) {
    return labelWidget;
  }

  let optionWidgets = [];
  for (let option of options) {
    if (option.value === displayName) {
      return (
        <div className={className}>
          <input type="hidden" name={name} value={displayName} />
          {labelWidget}
        </div>
      );
    }
    optionWidgets.push(
      <option key={option.value} value={option.value}>
        {option.label}
      </option>
    );
  }

  return (
    <div className={className}>
      {labelWidget}
      <select
        name={name}
        onChange={onChange}
        style={{ maxWidth: "150px" }}
        defaultValue={state[name]}
        {...args}
      >
        {optionWidgets}
      </select>
    </div>
  );
}

function FullscreenOverlay({ children }: { children: React.ReactNode }) {
  const [fullscreen, setFullscreen] = useState(false);

  // Prevent background scroll when fullscreen is open
  useEffect(() => {
    if (fullscreen) {
      const original = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      // Add ESC key handler
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") {
          setFullscreen(false);
        }
      };
      window.addEventListener("keydown", handleKeyDown);
      return () => {
        document.body.style.overflow = original;
        window.removeEventListener("keydown", handleKeyDown);
      };
    }
  }, [fullscreen]);

  if (fullscreen) {
    let overlay = (
      <div
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          width: "100vw",
          height: "100vh",
          zIndex: 999999,
          background: "rgba(255,255,255,0.85)",
          backdropFilter: "blur(16px) saturate(180%)",
          WebkitBackdropFilter: "blur(16px) saturate(180%)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            width: "80%",
            height: "80%",
            position: "relative",
          }}
        >
          {/* Close button */}
          <button
            aria-label="Close fullscreen table"
            onClick={() => setFullscreen(false)}
            style={{
              position: "absolute",
              top: -16,
              right: -16,
              zIndex: 1001,
              borderRadius: "50%",
              width: 40,
              height: 40,
              background: "#fff",
              border: "1px solid #ccc",
              boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: "pointer",
              fontSize: 24,
            }}
          >
            <i className="fa fa-times" aria-hidden="true"></i>
          </button>
          {/* Table */}
          {children}
        </div>
      </div>
    );
    return ReactDOM.createPortal(overlay, document.body);
  } else {
    return (
      <div style={{ position: "relative" }}>
        {/* Table */}
        <div style={{ height: 300 }}>{children}</div>
        {/* Expand button */}
        <button
          aria-label="Expand table"
          onClick={() => setFullscreen(true)}
          style={{
            position: "absolute",
            bottom: -10,
            right: -10,
            zIndex: 2,
            borderRadius: "50%",
            width: 28,
            height: 28,
            background: "#fff",
            border: "1px solid #ccc",
            boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
          }}
        >
          {/* FontAwesome expand icon */}
          <i
            className="fa-solid fa-sm fa-up-right-and-down-left-from-center"
            aria-hidden="true"
          ></i>
        </button>
      </div>
    );
  }
}
