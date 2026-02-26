import { Dialog, DialogContent } from '../chat/ui/Dialog'
import { SkillBrowserModal } from './SkillBrowserModal'
import { ToolBrowserModal } from './ToolBrowserModal'

interface SlashCommandModalProps {
  modal: 'skills' | 'gobby' | 'mcp' | null
  onClose: () => void
  onSendMessage: (content: string, injectContext: string) => void
  onRunSkill: (skillName: string) => void
}

export function SlashCommandModal({ modal, onClose, onSendMessage, onRunSkill }: SlashCommandModalProps) {
  if (!modal) return null

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-4xl h-[80vh] p-0 overflow-hidden flex flex-col">
        {modal === 'skills' && (
          <SkillBrowserModal onRunSkill={onRunSkill} onClose={onClose} />
        )}
        {modal === 'gobby' && (
          <ToolBrowserModal filter="internal" onSendMessage={onSendMessage} onClose={onClose} />
        )}
        {modal === 'mcp' && (
          <ToolBrowserModal filter="external" onSendMessage={onSendMessage} onClose={onClose} />
        )}
      </DialogContent>
    </Dialog>
  )
}
