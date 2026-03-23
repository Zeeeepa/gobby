import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ArtifactsTab } from '../ArtifactsTab'
import type { Artifact } from '../../../types/artifacts'

// Mock ArtifactPanel
vi.mock('../../chat/artifacts/ArtifactPanel', () => ({
  ArtifactPanel: ({ artifact, onMinimize, onMaximize, onBack }: any) => (
    <div data-testid="artifact-panel">
      <div data-testid="artifact-title">{artifact.title}</div>
      <button onClick={onMinimize} data-testid="btn-minimize">Minimize</button>
      <button onClick={onMaximize} data-testid="btn-maximize">Maximize</button>
      {onBack && <button onClick={onBack} data-testid="btn-back">Back</button>}
    </div>
  ),
}))

describe('ArtifactsTab', () => {
  const mockArtifacts = new Map<string, Artifact>([
    [
      'a1',
      {
        id: 'a1',
        type: 'code',
        title: 'Script.py',
        language: 'python',
        versions: [{ content: 'print("hello")', timestamp: new Date() }],
        currentVersionIndex: 0,
      },
    ],
    [
      'a2',
      {
        id: 'a2',
        type: 'text',
        title: 'Notes.md',
        language: 'markdown',
        versions: [{ content: '# Notes', timestamp: new Date() }],
        currentVersionIndex: 0,
      },
    ],
  ])

  const defaultProps = {
    artifacts: mockArtifacts,
    artifact: null,
    onOpenArtifact: vi.fn(),
    onClose: vi.fn(),
    onSetVersion: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders history list when no artifact is active', () => {
    render(<ArtifactsTab {...defaultProps} />)

    expect(screen.getByText('Artifact History')).toBeTruthy()
    expect(screen.getByText('Script.py')).toBeTruthy()
    expect(screen.getByText('Notes.md')).toBeTruthy()
    expect(screen.getByText('python')).toBeTruthy()
    expect(screen.getByText('text')).toBeTruthy()
  })

  it('calls onOpenArtifact when an item is clicked in history', () => {
    const onOpenArtifact = vi.fn()
    render(<ArtifactsTab {...defaultProps} onOpenArtifact={onOpenArtifact} />)

    fireEvent.click(screen.getByText('Script.py'))
    expect(onOpenArtifact).toHaveBeenCalledWith('a1')
  })

  it('renders ArtifactPanel when an artifact is active', () => {
    render(<ArtifactsTab {...defaultProps} artifact={mockArtifacts.get('a1')!} />)

    expect(screen.getByTestId('artifact-panel')).toBeTruthy()
    expect(screen.getByTestId('artifact-title')).toHaveTextContent('Script.py')
  })

  it('shows Back button in ArtifactPanel when multiple artifacts exist', () => {
    render(<ArtifactsTab {...defaultProps} artifact={mockArtifacts.get('a1')!} />)

    expect(screen.queryByTestId('btn-back')).toBeTruthy()
  })

  it('does not show Back button in ArtifactPanel when only one artifact exists', () => {
    const singleArtifact = new Map<string, Artifact>([['a1', mockArtifacts.get('a1')!]])
    render(<ArtifactsTab {...defaultProps} artifacts={singleArtifact} artifact={mockArtifacts.get('a1')!} />)

    expect(screen.queryByTestId('btn-back')).toBeFalsy()
  })

  it('calls onMinimize/onMaximize when buttons clicked', () => {
    const onMinimize = vi.fn()
    const onMaximize = vi.fn()
    render(
      <ArtifactsTab
        {...defaultProps}
        artifact={mockArtifacts.get('a1')!}
        onMinimize={onMinimize}
        onMaximize={onMaximize}
      />,
    )

    fireEvent.click(screen.getByTestId('btn-minimize'))
    expect(onMinimize).toHaveBeenCalled()

    fireEvent.click(screen.getByTestId('btn-maximize'))
    expect(onMaximize).toHaveBeenCalled()
  })
})
