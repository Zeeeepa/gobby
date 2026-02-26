import { describe, it, expect, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { resolveBoundValue, resolveActionContext, A2UISurfaceState } from '../types';
import { A2UIRenderer } from '../A2UIRenderer';

describe('A2UI Types & Utilities', () => {
  it('resolves BoundValue from literalString', () => {
    expect(resolveBoundValue({ literalString: 'Hello' })).toBe('Hello');
  });

  it('resolves BoundValue from dataModel path', () => {
    const dataModel = { user: { name: 'Alice' } };
    expect(resolveBoundValue({ path: 'user.name' }, dataModel)).toBe('Alice');
  });

  it('resolves ActionContext', () => {
    const dataModel = { count: 42 };
    const context = {
      val1: { literalString: 'static' },
      val2: { path: 'count' }
    };
    expect(resolveActionContext(context, dataModel)).toEqual({
      val1: 'static',
      val2: 42
    });
  });
});

describe('A2UIRenderer (Server Render)', () => {
  it('builds tree with known components and resolves bound values', () => {
    const surfaceState: A2UISurfaceState = {
      canvasId: 'c1',
      conversationId: 'conv1',
      mode: 'a2ui',
      surface: {
        root: { type: 'Card', label: { literalString: 'My Card' }, children: { explicitList: ['text1'] } },
        text1: { type: 'Text', text: { path: 'message' } }
      },
      dataModel: { message: 'Hello World' },
      rootComponentId: 'root',
      completed: false
    };

    const html = renderToStaticMarkup(
      <A2UIRenderer 
        surfaceState={surfaceState} 
        onAction={vi.fn()} 
      />
    );

    // Card label
    expect(html).toContain('My Card');
    // Resolved text from data model
    expect(html).toContain('Hello World');
  });

  it('renders error for unknown type', () => {
    const surfaceState: A2UISurfaceState = {
      canvasId: 'c1',
      conversationId: 'conv1',
      mode: 'a2ui',
      surface: {
        root: { type: 'UnknownComponent' }
      },
      dataModel: {},
      rootComponentId: 'root',
      completed: false
    };

    const html = renderToStaticMarkup(
      <A2UIRenderer 
        surfaceState={surfaceState} 
        onAction={vi.fn()} 
      />
    );

    expect(html).toContain('Unknown type: UnknownComponent');
  });
});
