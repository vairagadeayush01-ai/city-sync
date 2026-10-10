import { useEffect, useRef, useState } from 'react'
import { io } from 'socket.io-client'

const SOCKET_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

let _socket = null

function getSocket() {
  if (!_socket) {
    _socket = io(SOCKET_URL, {
      transports: ['websocket', 'polling'],
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
    })
  }
  return _socket
}

export function useSocket(wardId) {
  const [connected, setConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState(null)
  const socketRef = useRef(null)

  useEffect(() => {
    const socket = getSocket()
    socketRef.current = socket

    socket.on('connect', () => {
      setConnected(true)
      // Subscribe to ward room for officer map updates
      if (wardId) socket.emit('subscribe_ward', { ward_id: wardId })
    })

    socket.on('disconnect', () => setConnected(false))

    // Real-time events
    const handlers = {
      'ticket.update': (data) => setLastEvent({ type: 'ticket.update', data, ts: Date.now() }),
      'priority.boost': (data) => setLastEvent({ type: 'priority.boost', data, ts: Date.now() }),
      'ticket.created': (data) => setLastEvent({ type: 'ticket.created', data, ts: Date.now() }),
      'resolution.confirmed': (data) => setLastEvent({ type: 'resolution.confirmed', data, ts: Date.now() }),
    }

    Object.entries(handlers).forEach(([event, handler]) => socket.on(event, handler))

    return () => {
      Object.entries(handlers).forEach(([event, handler]) => socket.off(event, handler))
    }
  }, [wardId])

  const subscribeTicket = (ticketId) => {
    socketRef.current?.emit('subscribe_ticket', { ticket_id: ticketId })
  }

  return { connected, lastEvent, subscribeTicket, socket: socketRef.current }
}
