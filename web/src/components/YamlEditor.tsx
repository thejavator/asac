import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { yaml } from "@codemirror/lang-yaml";
import { Decoration, EditorView, drawSelection, keymap, lineNumbers } from "@codemirror/view";
import { EditorState, RangeSetBuilder, StateEffect, StateField } from "@codemirror/state";
import { useEffect, useRef } from "react";

/** Lines to mark as wrong, 1-based. */
const setBad = StateEffect.define<number[]>();
const badField = StateField.define({
  create: () => Decoration.none,
  update(deco, tr) {
    deco = deco.map(tr.changes);
    for (const e of tr.effects) {
      if (!e.is(setBad)) continue;
      const b = new RangeSetBuilder<Decoration>();
      for (const n of [...new Set(e.value)].sort((a, c) => a - c)) {
        if (n >= 1 && n <= tr.state.doc.lines) b.add(tr.state.doc.line(n).from, tr.state.doc.line(n).from, Decoration.line({ class: "cm-bad-line" }));
      }
      deco = b.finish();
    }
    return deco;
  },
  provide: (f) => EditorView.decorations.from(f),
});

export function YamlEditor({ value, onChange, badLines, readOnly, label }: {
  value: string; onChange: (v: string) => void; badLines: number[]; readOnly: boolean; label: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | undefined>(undefined);
  const cb = useRef(onChange);
  cb.current = onChange;

  useEffect(() => {
    const v = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: value,
        extensions: [
          EditorView.cspNonce.of(document.querySelector<HTMLMetaElement>('meta[name="csp-nonce"]')?.content ?? ""),
          lineNumbers(), history(), drawSelection(), yaml(), badField,
          keymap.of([...defaultKeymap, ...historyKeymap]),
          EditorState.readOnly.of(readOnly),
          EditorView.editable.of(!readOnly),
          EditorView.contentAttributes.of({ "aria-label": label, "aria-multiline": "true" }),
          EditorView.updateListener.of((u) => { if (u.docChanged) cb.current(u.state.doc.toString()); }),
        ],
      }),
    });
    view.current = v;
    return () => v.destroy();
    // the editor is created once per mount; later value changes are applied below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly, label]);

  useEffect(() => {
    const v = view.current;
    if (v && v.state.doc.toString() !== value) v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value } });
  }, [value]);

  useEffect(() => { view.current?.dispatch({ effects: setBad.of(badLines) }); }, [badLines, value]);

  return <div className="yaml-editor" ref={host} />;
}
