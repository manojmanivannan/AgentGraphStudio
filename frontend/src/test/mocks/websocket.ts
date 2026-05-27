/**
 * FakeWebSocket — replaces window.WebSocket in Vitest/jsdom tests.
 *
 * Usage:
 *   import { FakeWebSocket } from '@/test/mocks/websocket';
 *   beforeEach(() => { vi.stubGlobal('WebSocket', FakeWebSocket); FakeWebSocket.reset(); });
 *   afterEach(() => vi.unstubAllGlobals());
 *
 * After the code under test creates a WebSocket, get it via FakeWebSocket.lastInstance()
 * and call .simulateMessage(data) to inject incoming messages.
 */
export class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  static instances: FakeWebSocket[] = [];

  url: string;
  readyState: number = FakeWebSocket.OPEN;
  closed = false;
  sentMessages: string[] = [];

  onopen: ((evt: Event) => void) | null = null;
  onmessage: ((evt: MessageEvent) => void) | null = null;
  onerror: ((evt: Event) => void) | null = null;
  onclose: ((evt: CloseEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
    // Fire onopen asynchronously (microtask), matching real WebSocket behaviour
    // and allowing the caller to attach .onopen before it fires.
    Promise.resolve().then(() => {
      if (!this.closed) this.onopen?.(new Event("open"));
    });
  }

  send(data: string): void {
    if (this.closed) throw new Error("WebSocket is already closed");
    this.sentMessages.push(data);
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.(new CloseEvent("close", { wasClean: true, code: 1000 }));
  }

  /** Deliver a server-to-client message synchronously. */
  simulateMessage(data: unknown): void {
    const payload =
      typeof data === "string" ? data : JSON.stringify(data);
    this.onmessage?.(new MessageEvent("message", { data: payload }));
  }

  /** Remove all captured instances (call in beforeEach). */
  static reset(): void {
    FakeWebSocket.instances = [];
  }

  /** Get the most recently constructed FakeWebSocket instance. */
  static lastInstance(): FakeWebSocket | undefined {
    return FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
  }
}
