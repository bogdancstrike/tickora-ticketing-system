import { useEffect, useMemo, useRef } from 'react'
import * as d3 from 'd3'
import { Empty, Typography, theme as antTheme } from 'antd'
import dayjs from 'dayjs'
import type { AuditEventDto } from '@/api/tickets'

const STATUS_LANES = [
  'pending',
  'assigned_to_sector',
  'in_progress',
  'waiting_for_user',
  'on_hold',
  'reopened',
  'done',
  'closed',
  'cancelled',
] as const

const STATUS_COLORS: Record<string, string> = {
  pending: '#8c8c8c',
  assigned_to_sector: '#1677ff',
  in_progress: '#2f54eb',
  waiting_for_user: '#faad14',
  on_hold: '#fa8c16',
  reopened: '#722ed1',
  done: '#52c41a',
  closed: '#13a8a8',
  cancelled: '#cf1322',
}

interface Step {
  ts: Date
  status: string
  action: string
  actor: string
}

function deriveStatus(e: AuditEventDto): string | null {
  const next = (e.new_value as any)?.status
  if (next && STATUS_COLORS[next]) return next
  // Fall back to action-derived status (e.g. ticket_marked_done → done)
  const m = e.action.match(/^ticket_(.*)$/i)
  if (m) {
    const a = m[1].toLowerCase()
    if (a === 'marked_done') return 'done'
    if (a === 'closed') return 'closed'
    if (a === 'cancelled') return 'cancelled'
    if (a === 'reopened') return 'reopened'
    if (a === 'assigned_to_sector' || a === 'reassigned_to_sector') return 'assigned_to_sector'
    if (a === 'assigned_to_user' || a === 'reassigned' || a === 'assigned_to_me') return 'in_progress'
    if (a === 'unassigned') return 'assigned_to_sector'
    if (a === 'created') return 'pending'
  }
  return null
}

export function TicketEvolutionD3({ events }: { events: AuditEventDto[] }) {
  const ref = useRef<SVGSVGElement>(null)
  const { token } = antTheme.useToken()

  const steps = useMemo<Step[]>(() => {
    const out: Step[] = []
    let last: string | null = null
    for (const e of events.slice().reverse()) {
      const status = deriveStatus(e)
      if (!status || status === last) continue
      out.push({
        ts: new Date(e.created_at || ''),
        status,
        action: e.action,
        actor: e.actor_username || e.actor_user_id || 'system',
      })
      last = status
    }
    return out
  }, [events])

  useEffect(() => {
    if (!ref.current) return
    const svg = d3.select(ref.current)
    svg.selectAll('*').remove()

    const width = ref.current.clientWidth || 720
    const margin = { top: 24, right: 24, bottom: 36, left: 160 }
    const lanes = STATUS_LANES.filter((s) => steps.some((p) => p.status === s))
    const innerHeight = lanes.length * 38
    const height = innerHeight + margin.top + margin.bottom
    svg.attr('width', width).attr('height', height)

    if (steps.length === 0) return

    const innerWidth = width - margin.left - margin.right
    const xExtent = d3.extent(steps, (d) => d.ts) as [Date, Date]
    if (xExtent[0]?.getTime() === xExtent[1]?.getTime()) {
      // pad single-event tickets so the dot doesn't sit on the edge
      xExtent[1] = new Date(xExtent[1].getTime() + 1000 * 60 * 5)
    }
    const x = d3.scaleTime().domain(xExtent).range([0, innerWidth])
    const y = d3.scaleBand<string>().domain(lanes).range([0, innerHeight]).padding(0.4)

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    // Lane rows
    g.append('g')
      .selectAll('rect')
      .data(lanes)
      .enter()
      .append('rect')
      .attr('x', 0)
      .attr('y', (d) => y(d) || 0)
      .attr('width', innerWidth)
      .attr('height', y.bandwidth())
      .attr('fill', (_, i) => (i % 2 === 0 ? token.colorFillQuaternary : 'transparent'))
      .attr('rx', 4)

    // Lane labels
    svg.append('g')
      .attr('transform', `translate(0,${margin.top})`)
      .selectAll('text')
      .data(lanes)
      .enter()
      .append('text')
      .attr('x', margin.left - 12)
      .attr('y', (d) => (y(d) || 0) + y.bandwidth() / 2 + 4)
      .attr('text-anchor', 'end')
      .attr('fill', token.colorText)
      .style('font-size', '12px')
      .text((d) => d.replace(/_/g, ' '))

    // Lane status pip
    svg.append('g')
      .attr('transform', `translate(${margin.left - 6},${margin.top})`)
      .selectAll('circle')
      .data(lanes)
      .enter()
      .append('circle')
      .attr('cx', 0)
      .attr('cy', (d) => (y(d) || 0) + y.bandwidth() / 2)
      .attr('r', 4)
      .attr('fill', (d) => STATUS_COLORS[d] || '#888')

    // X axis
    const xAxis = d3.axisBottom(x).ticks(Math.min(8, steps.length + 1)).tickFormat((d) => dayjs(d as Date).format('MMM D HH:mm'))
    g.append('g')
      .attr('transform', `translate(0,${innerHeight})`)
      .call(xAxis as any)
      .selectAll('text')
      .attr('fill', token.colorTextSecondary)
      .style('font-size', '11px')
    g.selectAll('.domain, .tick line').attr('stroke', token.colorBorder)

    // Path connecting steps
    const line = d3.line<Step>()
      .x((d) => x(d.ts))
      .y((d) => (y(d.status) || 0) + y.bandwidth() / 2)
      .curve(d3.curveStepAfter)

    g.append('path')
      .datum(steps)
      .attr('d', line as any)
      .attr('fill', 'none')
      .attr('stroke', token.colorPrimary)
      .attr('stroke-width', 2)
      .attr('stroke-opacity', 0.6)

    // Tooltip
    let tooltip = d3.select<HTMLDivElement, unknown>('body').select<HTMLDivElement>('div.tickora-d3-tt')
    if (tooltip.empty()) {
      tooltip = d3.select<HTMLDivElement, unknown>('body')
        .append('div')
        .attr('class', 'tickora-d3-tt') as any
      tooltip
        .style('position', 'fixed')
        .style('pointer-events', 'none')
        .style('padding', '6px 10px')
        .style('border-radius', '6px')
        .style('background', token.colorBgElevated)
        .style('color', token.colorText)
        .style('border', `1px solid ${token.colorBorder}`)
        .style('font-size', '12px')
        .style('box-shadow', '0 4px 16px rgba(0,0,0,0.12)')
        .style('opacity', 0)
        .style('z-index', 9999)
    }

    // Step nodes
    g.append('g')
      .selectAll('circle')
      .data(steps)
      .enter()
      .append('circle')
      .attr('cx', (d) => x(d.ts))
      .attr('cy', (d) => (y(d.status) || 0) + y.bandwidth() / 2)
      .attr('r', 7)
      .attr('fill', (d) => STATUS_COLORS[d.status] || '#888')
      .attr('stroke', token.colorBgContainer)
      .attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .on('mouseover', (event, d) => {
        tooltip.html(
          `<div><b>${d.status.replace(/_/g, ' ')}</b></div>
           <div style="opacity:.75">${d.action}</div>
           <div style="opacity:.6;font-size:11px">${d.actor} · ${dayjs(d.ts).format('YYYY-MM-DD HH:mm')}</div>`
        )
        tooltip.style('opacity', 1)
      })
      .on('mousemove', (event) => {
        tooltip.style('left', `${(event as MouseEvent).clientX + 12}px`)
                .style('top', `${(event as MouseEvent).clientY + 12}px`)
      })
      .on('mouseout', () => tooltip.style('opacity', 0))
  }, [steps, token])

  if (steps.length === 0) {
    return <Empty description="Not enough state changes to plot" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  }

  return (
    <div>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Step transitions over time — hover a node for details.
      </Typography.Text>
      <svg ref={ref} style={{ display: 'block', marginTop: 8, width: '100%', overflow: 'visible' }} />
    </div>
  )
}
