import CodeMirror, {
  type Extension,
  type ReactCodeMirrorRef,
} from "@uiw/react-codemirror";
import { useEffect, useRef, useState } from "react";
import type { OnChange } from "~/app";
import { InputLabel, useGooeyStringInput } from "~/gooeyInput";
import { EditorView } from "@codemirror/view";
import { vscodeLightInit as theme } from "@uiw/codemirror-theme-vscode";

const linterDelay = 300;

const codeEditorExtensions: Record<string, () => Promise<Extension[]>> = {
  async jinja() {
    const { jinja } = await import("@codemirror/lang-jinja");
    const { markdown } = await import("@codemirror/lang-markdown");

    return [
      jinja({
        base: markdown({
          completeHTMLTags: false,
          extensions: {
            remove: ["HTMLBlock", "HTMLTag", "Link"],
          },
        }),
      }),
    ];
  },
  async json() {
    const { json, jsonParseLinter } = await import("@codemirror/lang-json");
    const { linter, lintGutter } = await import("@codemirror/lint");

    return [
      lintGutter(),
      json(),
      linter(jsonParseLinter(), { delay: linterDelay }),
    ];
  },
  async python() {
    const { python } = await import("@codemirror/lang-python");
    const { indentUnit } = await import("@codemirror/language");

    return [python(), indentUnit.of("    ")];
  },
  async javascript() {
    const { javascript } = await import("@codemirror/lang-javascript");
    const { linter, lintGutter } = await import("@codemirror/lint");
    const { JSHINT } = (await import("jshint")).default;

    let lintOptions = {
      esversion: 11,
      browser: true,
      lastsemic: true,
      asi: true,
      expr: true,
    };

    return [
      lintGutter(),
      javascript(),
      linter(
        (view: EditorView) => {
          const diagnostics: any = [];
          const codeText = view.state.doc.toJSON();
          JSHINT(codeText, lintOptions);
          const errors = JSHINT.data()?.errors;
          errors?.forEach((error) => {
            const selectedLine = view.state.doc.line(error.line);

            const diagnostic = {
              from: selectedLine.from,
              to: selectedLine.to,
              severity: "error",
              message: error.reason,
            };

            diagnostics.push(diagnostic);
          });
          return diagnostics;
        },
        { delay: linterDelay }
      ),
    ];
  },
};

export default function CodeEditor({
  props,
  state,
  onChange,
}: {
  props: Record<string, any>;
  onChange: OnChange;
  state: Record<string, any>;
}) {
  const {
    name,
    defaultValue,
    height,
    label,
    help,
    tooltipPlacement,
    language,
    ...args
  } = props;
  const [inputRef, value, setValue] = useGooeyStringInput<HTMLTextAreaElement>({
    state,
    name,
    defaultValue,
    args,
  });

  const handleChange = (val: string) => {
    setValue(val);
    // trigger the onChange event for Root Form
    // imitate the textarea onChange
    onChange({
      target: inputRef.current as HTMLElement,
    });
  };

  let [extensions, setExtensions] = useState<Extension[]>([]);

  useEffect(() => {
    codeEditorExtensions[language]?.call(null).then(setExtensions);
  }, [language]);

  extensions.push(EditorView.lineWrapping);

  const ref = useRef<ReactCodeMirrorRef>(null);

  useEffect(() => {
    ref.current?.editor
      ?.querySelector(".cm-content")
      ?.setAttribute("data-gramm", "false");
  }, [ref.current]);

  return (
    <div className="gui-input code-editor-wrapper position-relative">
      <InputLabel
        label={label}
        help={help}
        tooltipPlacement={tooltipPlacement}
      />
      <textarea
        ref={inputRef}
        name={name}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
        }}
      />
      <CodeMirror
        ref={ref}
        theme={theme({
          settings: {
            fontFamily: "monospace",
            fontSize: "14px",
          },
        })}
        value={value}
        onChange={handleChange}
        extensions={extensions}
        basicSetup={{ foldGutter: language !== "jinja" }}
        {...args}
      />
    </div>
  );
}
