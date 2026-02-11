import { useState, useEffect, useCallback, useRef } from 'react'

export interface CommandInfo {
  server: string
  tool: string
  name: string // display name: "server.tool"
  description: string
  isLocal?: boolean
  action?: string
}

interface ParsedCommand {
  server: string
  tool: string
  args: Record<string, string>
}

// Local commands that execute client-side actions (no MCP round-trip)
const LOCAL_COMMANDS: Array<{ name: string; description: string; action: string }> = [
  { name: 'settings', description: 'Open settings panel', action: 'open_settings' },
]

// Built-in aliases: /shortcut -> server.tool
const ALIASES: Record<string, { server: string; tool: string }> = {
  tasks: { server: 'gobby-tasks', tool: 'list_tasks' },
  skills: { server: 'gobby-skills', tool: 'list_skills' },
  memory: { server: 'gobby-memory', tool: 'search_memories' },
  servers: { server: 'gobby', tool: 'list_mcp_servers' },
}

export function useSlashCommands() {
  const [commands, setCommands] = useState<CommandInfo[]>([])
  const [filteredCommands, setFilteredCommands] = useState<CommandInfo[]>([])
  const fetchedRef = useRef(false)

  // Fetch tool list on mount
  useEffect(() => {
    if (fetchedRef.current) return
    fetchedRef.current = true

    const fetchTools = async () => {
      try {
        const baseUrl = ''

        const resp = await fetch(`${baseUrl}/mcp/tools`)
        if (!resp.ok) return

        const data = await resp.json()
        const cmds: CommandInfo[] = []

        // data is { server_name: [{ name, description }, ...], ... }
        for (const [server, tools] of Object.entries(data)) {
          if (!Array.isArray(tools)) continue
          for (const tool of tools) {
            cmds.push({
              server,
              tool: tool.name,
              name: `${server}.${tool.name}`,
              description: tool.description?.slice(0, 80) || '',
            })
          }
        }

        // Add local commands at the top
        for (const local of LOCAL_COMMANDS) {
          cmds.unshift({
            server: '_local',
            tool: local.action,
            name: local.name,
            description: local.description,
            isLocal: true,
            action: local.action,
          })
        }

        // Add alias entries at the top (after local commands)
        for (const [alias, target] of Object.entries(ALIASES)) {
          const existing = cmds.find(
            (c) => c.server === target.server && c.tool === target.tool
          )
          if (existing) {
            cmds.unshift({
              ...existing,
              name: alias,
            })
          }
        }

        setCommands(cmds)
      } catch (e) {
        console.error('Failed to fetch MCP tools:', e)
      }
    }

    fetchTools()
  }, [])

  // Parse "/server.tool key=val key2=val2" or "/alias key=val"
  const parseCommand = useCallback(
    (input: string): ParsedCommand | null => {
      if (!input.startsWith('/')) return null

      const trimmed = input.slice(1).trim()
      if (!trimmed) return null

      const parts = trimmed.split(/\s+/)
      const cmdName = parts[0]

      // Check local commands first
      const localCmd = LOCAL_COMMANDS.find((c) => c.name === cmdName)
      if (localCmd) {
        return { server: '_local', tool: localCmd.action, args: {} }
      }

      // Check alias first
      const alias = ALIASES[cmdName]
      let server: string
      let tool: string

      if (alias) {
        server = alias.server
        tool = alias.tool
      } else if (cmdName.includes('.')) {
        const dotIdx = cmdName.indexOf('.')
        server = cmdName.slice(0, dotIdx)
        tool = cmdName.slice(dotIdx + 1)
      } else {
        return null
      }

      // Parse key=value args
      const args: Record<string, string> = {}
      for (let i = 1; i < parts.length; i++) {
        const eqIdx = parts[i].indexOf('=')
        if (eqIdx > 0) {
          args[parts[i].slice(0, eqIdx)] = parts[i].slice(eqIdx + 1)
        }
      }

      return { server, tool, args }
    },
    []
  )

  // Filter commands by prefix
  const filterCommands = useCallback(
    (query: string) => {
      if (!query.startsWith('/')) {
        setFilteredCommands([])
        return
      }

      const search = query.slice(1).toLowerCase().split(/\s/)[0]
      if (!search) {
        // Show all aliases + first few commands
        setFilteredCommands(commands.slice(0, 15))
        return
      }

      const filtered = commands
        .filter((c) => c.name.toLowerCase().includes(search))
        .slice(0, 15)
      setFilteredCommands(filtered)
    },
    [commands]
  )

  return {
    commands,
    filteredCommands,
    parseCommand,
    filterCommands,
  }
}
