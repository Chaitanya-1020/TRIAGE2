"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { createCaseWebSocket } from "@/lib/api";
import type { WSMessage } from "@/types";

interface UseWebSocketOptions {
    caseId: string | null;
    onMessage: (msg: WSMessage) => void;
    enabled?: boolean;
}

interface UseWebSocketReturn {
    isConnected: boolean;
    send: (msg: object) => void;
    disconnect: () => void;
}

export function useWebSocket({
    caseId,
    onMessage,
    enabled = true,
}: UseWebSocketOptions): UseWebSocketReturn {
    const wsRef = useRef<WebSocket | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
    const mountedRef = useRef(true);

    const connect = useCallback(() => {
        if (!caseId || !enabled || !mountedRef.current) return;

        try {
            const ws = createCaseWebSocket(
                caseId,
                (msg) => {
                    if (mountedRef.current) onMessage(msg);
                },
                () => {
                    if (mountedRef.current) {
                        setIsConnected(false);
                        // Reconnect after 3s
                        reconnectTimeout.current = setTimeout(connect, 3000);
                    }
                }
            );

            ws.onopen = () => {
                if (mountedRef.current) setIsConnected(true);
            };

            ws.onclose = () => {
                if (mountedRef.current) {
                    setIsConnected(false);
                    reconnectTimeout.current = setTimeout(connect, 3000);
                }
            };

            wsRef.current = ws;
        } catch (err) {
            console.warn("WebSocket connection failed:", err);
        }
    }, [caseId, enabled, onMessage]);

    const disconnect = useCallback(() => {
        if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
        wsRef.current?.close();
        wsRef.current = null;
        setIsConnected(false);
    }, []);

    const send = useCallback((msg: object) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(msg));
        }
    }, []);

    useEffect(() => {
        mountedRef.current = true;
        if (caseId && enabled) connect();

        return () => {
            mountedRef.current = false;
            disconnect();
        };
    }, [caseId, enabled, connect, disconnect]);

    return { isConnected, send, disconnect };
}
