# Frontend - Reusable Chart Components Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor existing charts into a reusable component file and implement a new `WorkloadChart` for better data visualization.

**Architecture:** Centralize operational charts in `DashboardCharts.tsx` to ensure visual consistency and code reuse between the operational Monitor page and customizable Dashboards.

**Tech Stack:** React, TypeScript, Ant Design, ECharts (via `echarts-for-react`).

---

### Task 1: Create Reusable Chart Components File

**Files:**
- Create: `frontend/src/components/dashboard/DashboardCharts.tsx`

- [ ] **Step 1: Create `DashboardCharts.tsx` with `BreakdownChart` and `DoughnutChart`**

Copy implementation from `MonitorPage.tsx` and add proper exports and types.

```typescript
import React from 'react'
import ReactECharts from 'echarts-for-react'
import { Empty } from 'antd'

export interface MonitorBreakdown {
  key: string
  count: number
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
```

- [ ] **Step 2: Add `WorkloadChart` to `DashboardCharts.tsx`**

Implement the horizontal bar chart for user workload.

```typescript
export interface UserWorkload {
  assignee_user_id: string
  username?: string
  active: number
  done: number
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
```

### Task 2: Update MonitorPage to use Reusable Components

**Files:**
- Modify: `frontend/src/pages/MonitorPage.tsx`

- [ ] **Step 1: Import components and remove local definitions**

- [ ] **Step 2: Update `SectorPanel` to include `WorkloadChart`**

Add the chart in a new Column in the workload Row.

### Task 3: Verification

- [ ] **Step 1: Verify `MonitorPage` still works and shows the new chart**
- [ ] **Step 2: Verify code compiles and lint passes**
