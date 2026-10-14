import { useState } from 'react'
import { useTags } from '@/hooks/queries'
import { TagPill } from '../ui/Chip'
import { Field } from '../ui/Field'
import { Plus } from 'lucide-react'

interface TagInputProps {
  tags: string[]
  onChange: (tags: string[]) => void
}

const MAX_TAGS = 20

export function TagInput({ tags, onChange }: TagInputProps) {
  const [text, setText] = useState('')
  const { data: known } = useTags()

  function add(raw: string) {
    const parts = raw
      .split(',')
      .map((part) => part.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
    if (parts.length === 0) return
    const next = [...tags]
    for (const part of parts) {
      if (next.length < MAX_TAGS && !next.some((tag) => tag.toLowerCase() === part.toLowerCase())) next.push(part.slice(0, 50))
    }
    onChange(next)
    setText('')
  }

  const suggestions = (known ?? []).filter((tag) => !tags.some((selected) => selected.toLowerCase() === tag.name.toLowerCase())).slice(0, 12)

  return (
    <Field label="Tags" hint="Type a tag and press Enter, e.g. Blood, Thyroid, Dental." htmlFor="tag-input">
      <div className="space-y-2">
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {tags.map((tag) => (
              <TagPill key={tag} onRemove={() => onChange(tags.filter((entry) => entry !== tag))}>
                {tag}
              </TagPill>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <input
            id="tag-input"
            className="field-input"
            value={text}
            maxLength={50}
            enterKeyHint="done"
            placeholder="Add a tag"
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ',') {
                event.preventDefault()
                add(text)
              }
            }}
            onBlur={() => add(text)}
          />
          <button type="button" onClick={() => add(text)} aria-label="Add tag" className="grid size-12 shrink-0 place-items-center rounded-xl border border-line bg-white text-brand-700 hover:bg-wash">
            <Plus className="size-5" />
          </button>
        </div>
        {suggestions.length > 0 && (
          <div className="flex flex-wrap gap-2" aria-label="Existing tags">
            {suggestions.map((tag) => (
              <button
                key={tag.name}
                type="button"
                onClick={() => add(tag.name)}
                className="min-h-11 rounded-full border border-dashed border-line px-3 text-sm text-muted hover:bg-wash"
              >
                + {tag.name}
              </button>
            ))}
          </div>
        )}
      </div>
    </Field>
  )
}
