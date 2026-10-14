import { Link } from 'react-router-dom'
import { RECORD_TYPES, RECORD_TYPE_INFO } from '@/lib/recordTypes'
import { Modal } from '../ui/Modal'
import { TypeIcon } from './RecordCard'

/** The sheet the bottom nav's + opens: every record type in one grid, each opening that type's form. */
export function TypePickerSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} title="Add record" onClose={onClose} swipeToClose>
      <ul className="grid grid-cols-3 gap-2">
        {RECORD_TYPES.map((type) => (
          <li key={type}>
            <Link
              to={`/add/${type}`}
              onClick={onClose}
              className="flex min-h-24 flex-col items-center justify-center gap-2 rounded-2xl border border-line bg-card p-2 text-center text-sm font-semibold leading-tight transition hover:bg-wash active:bg-wash"
            >
              <TypeIcon type={type} className="size-11" />
              {RECORD_TYPE_INFO[type].label}
            </Link>
          </li>
        ))}
      </ul>
    </Modal>
  )
}
