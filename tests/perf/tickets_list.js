// Tickets-list perf: hits GET /api/tickets across a representative filter mix.
//
// Goal: p95 < 700 ms on the 30M seed with the Phase-9 partial indexes
// (`idx_tickets_active_*`) in place. The reltuples fast-path applies for
// admin/auditor when no narrowing filter is present, so two of the four
// scenarios below test that path.

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5100';
const TOKEN = __ENV.TICKORA_TOKEN;

if (!TOKEN) {
  throw new Error('TICKORA_TOKEN env var is required (see tests/perf/README.md)');
}

const headers = {
  Authorization: `Bearer ${TOKEN}`,
  'Content-Type': 'application/json',
};

const ttfbTrend = new Trend('http_ttfb_ms', true);

export const options = {
  scenarios: {
    steady: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 50 },
        { duration: '2m',  target: 50 },
        { duration: '30s', target: 0 },
      ],
      gracefulStop: '15s',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<700'],
    http_req_failed:   ['rate<0.01'],
  },
};

export default function () {
  group('list_no_filter (fast-path reltuples count)', () => {
    const r = http.get(`${BASE_URL}/tickora/api/tickets?limit=20`, { headers });
    check(r, { 'status 200': (res) => res.status === 200 });
    ttfbTrend.add(r.timings.waiting);
  });

  group('list_status_in_progress', () => {
    const r = http.get(`${BASE_URL}/tickora/api/tickets?status=in_progress&limit=20`, { headers });
    check(r, { 'status 200': (res) => res.status === 200 });
  });

  group('list_priority_critical', () => {
    const r = http.get(`${BASE_URL}/tickora/api/tickets?priority=critical&limit=20`, { headers });
    check(r, { 'status 200': (res) => res.status === 200 });
  });

  group('list_search_text', () => {
    const r = http.get(`${BASE_URL}/tickora/api/tickets?search=outage&limit=20`, { headers });
    check(r, { 'status 200': (res) => res.status === 200 });
  });

  sleep(0.2);
}
