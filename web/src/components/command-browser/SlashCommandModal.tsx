import { Dialog, DialogContent } from '../chat/ui/Dialog'
import { SkillBrowserModal } from './SkillBrowserModal'
import { ToolBrowserModal } from './ToolBrowserModal'

interface SlashCommandModalProps {
  modal: 'skills' | 'gobby' | 'mcp' | null
  onClose: () => void
  onExecuteTool: (server: string, tool: string, args: Record<string, unknown>) => void
  onRunSkill: (skillName: string) => void
}

export function SlashCommandModal({ modal, onClose, onExecuteTool, onRunSkill }: SlashCommandModalProps) {
  if (!modal) return null

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-4xl h-[80vh] p-0 overflow-hidden flex flex-col">
        {modal === 'skills' && (
          <SkillBrowserModal onRunSkill={onRunSkill} onClose={onClose} />
        )}
        {modal === 'gobby' && (
          <ToolBrowserModal filter="internal" onExecuteTool={onExecuteTool} onClose={onClose} />
        )}
        {modal === 'mcp' && (
          <ToolBrowserModal filter="external" onExecuteTool={onExecuteTool} onClose={onClose} />
        )}
      </DialogContent>
    </Dialog>
  )
}
