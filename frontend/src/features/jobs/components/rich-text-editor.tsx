"use client";

import { EditorContent, useEditor, useEditorState } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Bold, Heading2, Italic, Link2, List, ListOrdered } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useId, type ReactNode } from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/**
 * Minimal rich text (docs/08: headings, lists, bold, italic, links). Output is HTML that the
 * server sanitises with an allow-list on save (EC-JOB-12); the editor only offers allowed marks.
 */
export function RichTextEditor({
  label,
  value,
  onChange,
  description,
  name,
}: {
  label: string;
  value: string;
  onChange: (html: string) => void;
  description?: ReactNode;
  name: string;
}) {
  const t = useTranslations("jobs.editor");
  const labelId = useId();
  const descId = useId();
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: { levels: [2, 3, 4] },
        code: false,
        codeBlock: false,
        blockquote: false,
        horizontalRule: false,
        strike: false,
        underline: false,
        link: { openOnClick: false, protocols: ["http", "https", "mailto"] },
      }),
    ],
    content: value,
    editorProps: {
      attributes: {
        id: `field-${name}`,
        role: "textbox",
        "aria-multiline": "true",
        "aria-labelledby": labelId,
        ...(description ? { "aria-describedby": descId } : {}),
        class:
          "prose prose-sm max-w-none min-h-32 px-3 py-2 focus:outline-none [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-5 [&_ol]:pl-5 [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:font-semibold [&_a]:underline",
      },
    },
    onUpdate: ({ editor: e }) => onChange(e.isEmpty ? "" : e.getHTML()),
  });

  // Keep external resets (reload after a conflict) in sync without clobbering typing.
  useEffect(() => {
    if (
      editor &&
      !editor.isFocused &&
      value !== editor.getHTML() &&
      !(value === "" && editor.isEmpty)
    ) {
      editor.commands.setContent(value, { emitUpdate: false });
    }
  }, [editor, value]);

  const state = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      bold: e?.isActive("bold") ?? false,
      italic: e?.isActive("italic") ?? false,
      heading: e?.isActive("heading", { level: 2 }) ?? false,
      bullet: e?.isActive("bulletList") ?? false,
      ordered: e?.isActive("orderedList") ?? false,
      link: e?.isActive("link") ?? false,
    }),
  });

  const setLink = () => {
    if (!editor) return;
    const previous = editor.getAttributes("link").href as string | undefined;
    const url = window.prompt(t("linkPrompt"), previous ?? "https://");
    if (url === null) return;
    if (url === "") {
      editor.chain().focus().extendMarkRange("link").unsetLink().run();
      return;
    }
    if (!/^(https?:|mailto:)/i.test(url)) return;
    editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
  };

  const tools: { key: string; icon: ReactNode; active: boolean; run: () => void }[] = [
    {
      key: "bold",
      icon: <Bold />,
      active: !!state?.bold,
      run: () => editor?.chain().focus().toggleBold().run(),
    },
    {
      key: "italic",
      icon: <Italic />,
      active: !!state?.italic,
      run: () => editor?.chain().focus().toggleItalic().run(),
    },
    {
      key: "heading",
      icon: <Heading2 />,
      active: !!state?.heading,
      run: () => editor?.chain().focus().toggleHeading({ level: 2 }).run(),
    },
    {
      key: "bulletList",
      icon: <List />,
      active: !!state?.bullet,
      run: () => editor?.chain().focus().toggleBulletList().run(),
    },
    {
      key: "orderedList",
      icon: <ListOrdered />,
      active: !!state?.ordered,
      run: () => editor?.chain().focus().toggleOrderedList().run(),
    },
    { key: "link", icon: <Link2 />, active: !!state?.link, run: setLink },
  ];

  return (
    <div className="flex flex-col gap-1.5">
      <Label id={labelId} htmlFor={`field-${name}`}>
        {label}
      </Label>
      <div className="border-input focus-within:ring-ring/50 rounded-md border focus-within:ring-2">
        <div
          role="toolbar"
          aria-label={t("toolbar", { field: label })}
          className="flex flex-wrap gap-1 border-b p-1"
        >
          {tools.map((tool) => (
            <button
              key={tool.key}
              type="button"
              onClick={tool.run}
              aria-pressed={tool.active}
              aria-label={t(tool.key)}
              title={t(tool.key)}
              className={cn(
                "hover:bg-muted grid size-8 place-items-center rounded [&_svg]:size-4",
                tool.active && "bg-muted text-foreground",
              )}
            >
              {tool.icon}
            </button>
          ))}
        </div>
        <EditorContent editor={editor} />
      </div>
      {description ? (
        <p id={descId} className="text-muted-foreground text-xs">
          {description}
        </p>
      ) : null}
    </div>
  );
}
