import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = {
  content: string;
};

export function MarkdownPreview({ content }: Props) {
  return (
    <div className="text-sm text-text">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="font-mono text-xl mt-2 mb-3">{children}</h1>,
          h2: ({ children }) => <h2 className="font-mono text-lg mt-4 mb-2">{children}</h2>,
          h3: ({ children }) => <h3 className="font-mono text-base mt-4 mb-2">{children}</h3>,
          p: ({ children }) => <p className="my-2 text-text-muted">{children}</p>,
          a: ({ href, children }) => (
            <a
              href={href}
              className="text-accent hover:text-accent-hover underline underline-offset-4"
              target="_blank"
              rel="noreferrer"
            >
              {children}
            </a>
          ),
          ul: ({ children }) => <ul className="my-2 list-disc pl-5 text-text-muted">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 list-decimal pl-5 text-text-muted">{children}</ol>,
          li: ({ children }) => <li className="my-1">{children}</li>,
          code: ({ children }) => (
            <code className="rounded bg-bg-hover px-1 py-0.5 font-mono text-xs text-text">
              {children}
            </code>
          ),
          pre: ({ children }) => (
            <pre className="my-3 overflow-auto rounded-lg border border-border bg-bg px-3 py-2">
              {children}
            </pre>
          ),
          blockquote: ({ children }) => (
            <blockquote className="my-3 border-l-2 border-border-light pl-3 text-text-dim">
              {children}
            </blockquote>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

