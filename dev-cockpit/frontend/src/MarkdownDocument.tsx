import type { ReactNode } from 'react'

function inlineText(value: string): ReactNode {
  const parts: ReactNode[] = []
  const pattern = /(`[^`]+`|**[^*]+**|[[^]]+]([^)]+))/g
  let last = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(value)) !== null) {
    if (match.index > last) {
      parts.push(value.slice(last, match.index))
    }
    const token = match[0]
    if (token.startsWith('`')) {
      parts.push(<code key={`code-${match.index}`}>{token.slice(1, -1)}</code>)
    } else if (token.startsWith('**')) {
      parts.push(<strong key={`bold-${match.index}`}>{token.slice(2, -2)}</strong>)
    } else {
      const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
      if (link) {
        parts.push(
          <a
            key={`link-${match.index}`}
            href={link[2]}
            target="_blank"
            rel="noreferrer"
          >
            {link[1]}
          </a>,
        )
      } else {
        parts.push(token)
      }
    }
    last = match.index + token.length
  }

  if (last < value.length) {
    parts.push(value.slice(last))
  }
  return parts.length ? parts : value
}

type Block =
  | { kind: 'code'; lines: string[] }
  | { kind: 'table'; lines: string[] }
  | { kind: 'list'; ordered: boolean; lines: string[] }
  | { kind: 'paragraph'; lines: string[] }
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'quote'; lines: string[] }

function blocksFromMarkdown(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n')
  const blocks: Block[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]

    if (!line.trim()) {
      index += 1
      continue
    }

    if (line.trim().startsWith('```')) {
      const code: string[] = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        code.push(lines[index])
        index += 1
      }
      if (index < lines.length) index += 1
      blocks.push({ kind: 'code', lines: code })
      continue
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/)
    if (heading) {
      blocks.push({
        kind: 'heading',
        level: heading[1].length,
        text: heading[2].trim(),
      })
      index += 1
      continue
    }

    if (/^\s*\|.*\|\s*$/.test(line)) {
      const table: string[] = []
      while (index < lines.length && /^\s*\|.*\|\s*$/.test(lines[index])) {
        table.push(lines[index].trim())
        index += 1
      }
      blocks.push({ kind: 'table', lines: table })
      continue
    }

    if (/^\s*>\s?/.test(line)) {
      const quote: string[] = []
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^\s*>\s?/, ''))
        index += 1
      }
      blocks.push({ kind: 'quote', lines: quote })
      continue
    }

    const unordered = /^\s*[-*+]\s+/.test(line)
    const ordered = /^\s*\d+[.)]\s+/.test(line)
    if (unordered || ordered) {
      const list: string[] = []
      const listPattern = ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*+]\s+/
      while (index < lines.length && listPattern.test(lines[index])) {
        list.push(lines[index].replace(listPattern, ''))
        index += 1
      }
      blocks.push({ kind: 'list', ordered, lines: list })
      continue
    }

    const paragraph: string[] = [line.trim()]
    index += 1
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^(#{1,6})\s+/.test(lines[index]) &&
      !/^\s*[-*+]\s+/.test(lines[index]) &&
      !/^\s*\d+[.)]\s+/.test(lines[index]) &&
      !/^\s*>\s?/.test(lines[index]) &&
      !/^\s*\|.*\|\s*$/.test(lines[index]) &&
      !lines[index].trim().startsWith('```')
    ) {
      paragraph.push(lines[index].trim())
      index += 1
    }
    blocks.push({ kind: 'paragraph', lines: paragraph })
  }

  return blocks
}

export default function MarkdownDocument({
  markdown,
  compact = false,
}: {
  markdown: string
  compact?: boolean
}) {
  if (!markdown.trim()) {
    return <p className="role-detail-muted">Aucun contenu documenté.</p>
  }

  const blocks = blocksFromMarkdown(markdown)

  return (
    <div className={`cockpit-markdown ${compact ? 'compact' : ''}`}>
      {blocks.map((block, index) => {
        if (block.kind === 'heading') {
          const Tag =
            block.level <= 2 ? 'h3' : block.level === 3 ? 'h4' : 'h5'
          return <Tag key={`heading-${index}`}>{inlineText(block.text)}</Tag>
        }

        if (block.kind === 'code') {
          return (
            <pre className="cockpit-markdown-code" key={`code-${index}`}>
              <code>{block.lines.join('\n')}</code>
            </pre>
          )
        }

        if (block.kind === 'table') {
          return (
            <pre className="cockpit-markdown-table" key={`table-${index}`}>
              {block.lines.join('\n')}
            </pre>
          )
        }

        if (block.kind === 'quote') {
          return (
            <blockquote key={`quote-${index}`}>
              {block.lines.map((line, lineIndex) => (
                <p key={`quote-line-${lineIndex}`}>{inlineText(line)}</p>
              ))}
            </blockquote>
          )
        }

        if (block.kind === 'list') {
          const ListTag = block.ordered ? 'ol' : 'ul'
          return (
            <ListTag key={`list-${index}`}>
              {block.lines.map((line, lineIndex) => {
                const checkbox = line.match(/^\[([xX ])\]\s*(.*)$/)
                return (
                  <li key={`item-${lineIndex}`}>
                    {checkbox ? (
                      <>
                        <span
                          className={`markdown-check ${checkbox[1].toLowerCase() === 'x' ? 'done' : ''}`}
                          aria-hidden="true"
                        >
                          {checkbox[1].toLowerCase() === 'x' ? '✓' : '□'}
                        </span>{' '}
                        {inlineText(checkbox[2])}
                      </>
                    ) : (
                      inlineText(line)
                    )}
                  </li>
                )
              })}
            </ListTag>
          )
        }

        return (
          <p key={`paragraph-${index}`}>
            {inlineText(block.lines.join(' '))}
          </p>
        )
      })}
    </div>
  )
}
