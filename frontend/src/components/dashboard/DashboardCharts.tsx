import React from 'react'
import ReactECharts from 'echarts-for-react'
import { Empty } from 'antd'
import { type MonitorBreakdown } from '@/api/tickets'

export interface UserWorkload {
  assignee_user_id: string
  username?: string
  active: number
  done: number
}

export function labelize(value: string) {
  return value.split('_').join(' ')
}

export function BreakdownChart({ data, title, color = '#1677ff', height = 240 }: { data: MonitorBreakdown[]; title: string; color?: string; height?: number }) {
  if (!data?.length) return <Empty description="No data" image={Empty.PRESENTED_IMAGE_SIMPLE} />

  const option = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, data: [title] },
    grid: { left: '3%', right: '4%', bottom: '3%', top: 34, containLabel: true },
    xAxis: { type: 'category', data: data.map((i) => labelize(i.key)), axisTick: { alignWithLabel: true } },
    yAxis: { type: 'value' },
    series: [{ name: title, type: 'bar', barWidth: '60%', data: data.map((i) => i.count), itemStyle: { color, borderRadius: [4, 4, 0, 0] } }],
  }
  return <ReactECharts option={option} style={{ height }} />
}

export function DoughnutChart({ data, title, height = 240 }: { data: MonitorBreakdown[]; title: string; height?: number }) {
  if (!data?.length) return <Empty description="No data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  const option = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, type: 'scroll' },
    series: [{
      name: title,
      type: 'pie',
      radius: ['45%', '70%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 4, borderColor: 'transparent', borderWidth: 2 },
      label: { show: false },
      labelLine: { show: false },
      data: data.map((i) => ({ name: labelize(i.key), value: i.count })),
    }],
  }
  return <ReactECharts option={option} style={{ height }} />
}

export function WorkloadChart({ data, height = 300 }: { data: UserWorkload[]; height?: number }) {
  if (!data?.length) return <Empty description="No workload data" image={Empty.PRESENTED_IMAGE_SIMPLE} />

  const option = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['Active', 'Done'] },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: data.map(d => d.username || d.assignee_user_id) },
    series: [
      {
        name: 'Active',
        type: 'bar',
        stack: 'total',
        label: { show: true },
        emphasis: { focus: 'series' },
        data: data.map(d => d.active),
        itemStyle: { color: '#1677ff' }
      },
      {
        name: 'Done',
        type: 'bar',
        stack: 'total',
        label: { show: true },
        emphasis: { focus: 'series' },
        data: data.map(d => d.done),
        itemStyle: { color: '#52c41a' }
      }
    ]
  }
  return <ReactECharts option={option} style={{ height }} />
}
