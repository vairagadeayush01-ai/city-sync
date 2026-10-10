import { useState, useEffect, useCallback } from 'react'
import { listTickets, getTicket } from '../utils/api'

export function useTickets(filters = {}) {
  const [tickets, setTickets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchTickets = useCallback(async () => {
    try {
      setLoading(true)
      const res = await listTickets(filters)
      setTickets(res.data.tickets || [])
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [JSON.stringify(filters)])

  useEffect(() => {
    fetchTickets()
    const interval = setInterval(fetchTickets, 10000) // Poll every 10s
    return () => clearInterval(interval)
  }, [fetchTickets])

  const addOrUpdateTicket = useCallback((ticketData) => {
    setTickets(prev => {
      const idx = prev.findIndex(t => t.ticket_id === ticketData.ticket_id)
      if (idx >= 0) {
        const updated = [...prev]
        updated[idx] = { ...updated[idx], ...ticketData }
        return updated.sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0))
      }
      return [ticketData, ...prev]
    })
  }, [])

  return { tickets, loading, error, refetch: fetchTickets, addOrUpdateTicket }
}
