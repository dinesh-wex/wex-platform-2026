/** Derive WebSocket URL from the API URL env var (http→ws, https→wss). */
function getWsUrl(): string {
  const api = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  return api.replace(/^http/, 'ws');
}

export class WexWebSocket {
  private ws: WebSocket | null = null;
  private listeners: Map<string, ((data: any) => void)[]> = new Map();

  connect(warehouseId: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const wsUrl = getWsUrl();
      this.ws = new WebSocket(`${wsUrl}/ws/activation/${warehouseId}`);

      this.ws.onopen = () => resolve();
      this.ws.onerror = (e) => reject(e);

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          const handlers = this.listeners.get(msg.type) || [];
          handlers.forEach(h => h(msg.data));
        } catch (e) {
          console.error('WebSocket message parse error:', e);
        }
      };

      this.ws.onclose = () => {
        const handlers = this.listeners.get('close') || [];
        handlers.forEach(h => h(null));
      };
    });
  }

  on(type: string, handler: (data: any) => void) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type)!.push(handler);
    return () => {
      const handlers = this.listeners.get(type);
      if (handlers) {
        const idx = handlers.indexOf(handler);
        if (idx >= 0) handlers.splice(idx, 1);
      }
    };
  }

  send(data: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  disconnect() {
    this.ws?.close();
    this.ws = null;
  }
}


// ---------------------------------------------------------------------------
// Admin event types
// ---------------------------------------------------------------------------

export type AdminEventType =
  | 'deal_update'
  | 'match_created'
  | 'agent_activity'
  | 'toggle_update'
  | 'ledger_entry';

export interface AdminEvent<T = Record<string, unknown>> {
  type: AdminEventType;
  data: T;
  timestamp: string;
}

export type AdminEventHandler<T = Record<string, unknown>> = (event: AdminEvent<T>) => void;

// ---------------------------------------------------------------------------
// Admin WebSocket client
// ---------------------------------------------------------------------------

const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY_MS = 3_000;

export class AdminWebSocket {
  private ws: WebSocket | null = null;
  private listeners: Map<string, AdminEventHandler[]> = new Map();
  private reconnectAttempts = 0;
  private shouldReconnect = true;
  private pingInterval: ReturnType<typeof setInterval> | null = null;

  /**
   * Connect to the admin dashboard WebSocket.
   * Resolves once the connection is open.
   */
  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const wsUrl = getWsUrl();
      this.ws = new WebSocket(`${wsUrl}/ws/admin`);
      this.shouldReconnect = true;

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.startPing();
        resolve();
      };

      this.ws.onerror = (e) => {
        if (this.reconnectAttempts === 0) {
          reject(e);
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const msg: AdminEvent = JSON.parse(event.data);
          // Skip pong responses
          if ((msg as any).type === 'pong') return;

          // Dispatch to type-specific handlers
          const handlers = this.listeners.get(msg.type) || [];
          handlers.forEach(h => h(msg));

          // Also dispatch to wildcard '*' handlers
          const wildcardHandlers = this.listeners.get('*') || [];
          wildcardHandlers.forEach(h => h(msg));
        } catch (e) {
          console.error('Admin WebSocket message parse error:', e);
        }
      };

      this.ws.onclose = () => {
        this.stopPing();
        const handlers = this.listeners.get('close') || [];
        handlers.forEach(h => h({ type: 'close' as any, data: {}, timestamp: new Date().toISOString() }));

        if (this.shouldReconnect && this.reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
          this.reconnectAttempts++;
          console.log(
            `Admin WS reconnecting (attempt ${this.reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`
          );
          setTimeout(() => {
            this.connect().catch(() => {
              /* swallow – onclose will fire again if needed */
            });
          }, RECONNECT_DELAY_MS);
        }
      };
    });
  }

  /**
   * Register a handler for a specific admin event type.
   * Pass '*' to listen to all event types.
   * Returns an unsubscribe function.
   */
  on<T = Record<string, unknown>>(
    type: AdminEventType | 'close' | '*',
    handler: AdminEventHandler<T>,
  ): () => void {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type)!.push(handler as AdminEventHandler);
    return () => {
      const handlers = this.listeners.get(type);
      if (handlers) {
        const idx = handlers.indexOf(handler as AdminEventHandler);
        if (idx >= 0) handlers.splice(idx, 1);
      }
    };
  }

  /**
   * Cleanly disconnect. No auto-reconnect will be attempted.
   */
  disconnect() {
    this.shouldReconnect = false;
    this.stopPing();
    this.ws?.close();
    this.ws = null;
  }

  /** Whether the WebSocket is currently open. */
  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  // -- internal helpers -----------------------------------------------------

  private startPing() {
    this.stopPing();
    this.pingInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30_000);
  }

  private stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }
}
