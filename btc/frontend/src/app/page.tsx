'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart, ColorType, CandlestickSeries, LineSeries, createSeriesMarkers } from 'lightweight-charts'
import { API_BASE } from '@/lib/utils'

// ─── Types ────────────────────────────────────────────────────────────────

interface KlineData {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface TradeRecord {
  pair: string
  type: 'entry' | 'exit'
  side: 'long' | 'short'
  price: number
  size: number
  pnl?: number
  pnl_pct?: number
  cost?: number
  fee?: number
  timestamp: string
  duration?: string
  enter_tag?: string
  exit_reason?: string
  leverage?: number
  entry_price?: number
}

interface Metrics {
  total_trades: number
  total_profit_usdt: number
  total_profit_pct: number
  win_rate: number
  sharpe_ratio: number
  max_drawdown_pct: number
  avg_profit_pct: number
  starting_balance: number
  final_balance: number
}

interface BacktestResult {
  success: boolean
  metrics: Metrics
  trades: TradeRecord[]
  equity_curve: { timestamp: string; equity: number }[]
  config: {
    strategy: string
    pairs: string[]
    timeframe: string
    timerange: string
    stake_amount: number
    initial_balance: number
    max_open_trades: number
    leverage: number
    fee: number
    trading_mode: string
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────

function fmt(v: number, d = 2) { return Number(v).toFixed(d) }
function pct(v: number) { return v >= 0 ? `+${fmt(v)}%` : `${fmt(v)}%` }
function usdt(v: number) { return v >= 0 ? `+$${fmt(v)}` : `-$${fmt(Math.abs(v))}` }

// ─── Config Panel ─────────────────────────────────────────────────────────

const PAIRS = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT']
const TFS = ['1m', '5m', '15m', '1h', '4h', '1d']
const RANGES = [
  { label: '7天', value: '7' },
  { label: '30天', value: '30' },
  { label: '90天', value: '90' },
  { label: '自定义...', value: '' },
]

function getTimerange(days: number): string {
  // Generate timerange like 20251001-20251231
  const end = new Date()
  const start = new Date(end.getTime() - days * 86400000)
  const fmt = (d: Date) =>
    `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`
  return `${fmt(start)}-${fmt(end)}`
}

function ConfigPanel({
  config, onChange, onRun, running, strategyList,
}: {
  config: any
  onChange: (updates: any) => void
  onRun: () => void
  running: boolean
  strategyList: string[]
}) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs text-gray-500">策略</label>
          <select className="w-full text-sm border rounded px-2 py-1"
            value={config.strategy}
            onChange={e => onChange({ strategy: e.target.value })}
          >
            {strategyList.filter(s => !s.includes('Test') && !s.includes('Sample') && !s.includes('MacdStrategy') && !s.includes('EmaCross') && !s.includes('Candlestick') && !s.includes('Vegas') && !s.includes('MacdDivergence') && !s.includes('TimeStrategy') && !s.includes('Aggressive') && !s.includes('BigTrend') && !s.includes('MultiTF') && !s.includes('VolatilityBreakout')).map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500">交易对（点选多个）</label>
          <div className="flex flex-wrap gap-1">
            {PAIRS.map(p => (
              <label key={p} className="flex items-center gap-1 text-xs bg-gray-50 rounded px-2 py-1 cursor-pointer hover:bg-gray-100">
                <input type="checkbox" checked={config.pairs.includes(p)}
                  onChange={() => {
                    const newPairs = config.pairs.includes(p)
                      ? config.pairs.filter((x: string) => x !== p)
                      : [...config.pairs, p]
                    onChange({ pairs: newPairs.length > 0 ? newPairs : [p] })
                  }} />
                {p.split('/')[0]}
              </label>
            ))}
          </div>
        </div>
        <div>
          <label className="text-xs text-gray-500">时间粒度</label>
          <select className="w-full text-sm border rounded px-2 py-1"
            value={config.timeframe}
            onChange={e => onChange({ timeframe: e.target.value })}
          >
            {TFS.map(t => <option key={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500">时间范围</label>
          <div className="flex gap-1 items-center mb-1.5">
            <input className="flex-1 text-xs border rounded px-2 py-1.5 min-w-0" type="date"
              value={config.customStart ? `${config.customStart.slice(0,4)}-${config.customStart.slice(4,6)}-${config.customStart.slice(6,8)}` : ''}
              onChange={e => onChange({ customStart: e.target.value.replace(/-/g,'') })}
            />
            <span className="text-gray-400 text-xs shrink-0">~</span>
            <input className="flex-1 text-xs border rounded px-2 py-1.5 min-w-0" type="date"
              value={config.customEnd ? `${config.customEnd.slice(0,4)}-${config.customEnd.slice(4,6)}-${config.customEnd.slice(6,8)}` : ''}
              onChange={e => onChange({ customEnd: e.target.value.replace(/-/g,'') })}
            />
          </div>
          <div className="flex flex-wrap gap-1">
            {[
              { label: '7天', days: 7 },
              { label: '30天', days: 30 },
              { label: '90天', days: 90 },
              { label: '365天', days: 365 },
              { label: '今年', days: 0 },
            ].map(btn => {
              const now = new Date()
              const end = `${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}`
              let start = ''
              if (btn.days === 0) {
                start = `${now.getFullYear()}0101`
              } else {
                const s = new Date(now.getTime() - btn.days * 86400000)
                start = `${s.getFullYear()}${String(s.getMonth()+1).padStart(2,'0')}${String(s.getDate()).padStart(2,'0')}`
              }
              const isActive = config.customStart === start && config.customEnd === end
              return (
                <button key={btn.label}
                  className={`text-[11px] px-2 py-1 rounded-md font-medium transition-all ${isActive ? 'bg-blue-600 text-white shadow-sm' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
                  onClick={() => onChange({ customStart: start, customEnd: end })}
                >{btn.label}</button>
              )
            })}
          </div>
        </div>
        <div>
          <label className="text-xs text-gray-500">本金 (USDT)</label>
          <input className="w-full text-sm border rounded px-2 py-1" type="number"
            value={config.initial_balance} min={100}
            onChange={e => onChange({ initial_balance: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="text-xs text-gray-500">每笔投入</label>
          <input className="w-full text-sm border rounded px-2 py-1" type="number"
            value={config.stake_amount} min={10}
            onChange={e => onChange({ stake_amount: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="text-xs text-gray-500">杠杆</label>
          <input className="w-full text-sm border rounded px-2 py-1" type="number"
            value={config.leverage} min={1} max={125}
            onChange={e => onChange({ leverage: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="text-xs text-gray-500">费率 (%)</label>
          <input className="w-full text-sm border rounded px-2 py-1" type="number"
            value={config.fee} step={0.001}
            onChange={e => onChange({ fee: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="text-xs text-gray-500">最大持仓数</label>
          <input className="w-full text-sm border rounded px-2 py-1" type="number"
            value={config.max_open_trades} min={1}
            onChange={e => onChange({ max_open_trades: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="text-xs text-gray-500">滑点 (%)</label>
          <input className="w-full text-sm border rounded px-2 py-1" type="number"
            value={config.slippage} step={0.001} min={0}
            onChange={e => onChange({ slippage: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="text-xs text-gray-500">仓位占比 (%)</label>
          <input className="w-full text-sm border rounded px-2 py-1" type="number"
            value={config.position_pct} min={5} max={100}
            onChange={e => onChange({ position_pct: Number(e.target.value), stake_amount: Math.round(config.initial_balance * Number(e.target.value) / 100 / 100) * 100 })}
          />
          <div className="text-[9px] text-gray-400 mt-0.5">每笔 = 本金×占比 = ${config.initial_balance}×{config.position_pct}% = ${Math.round(config.initial_balance*config.position_pct/100)}</div>
        </div>
        <div>
          <label className="text-xs text-gray-500">单笔止损 (%)</label>
          <input className="w-full text-sm border rounded px-2 py-1" type="number"
            value={config.custom_stoploss} step={0.1} min={0.1}
            onChange={e => onChange({ custom_stoploss: Number(e.target.value) })}
          />
          <div className="text-[9px] text-gray-400 mt-0.5">最大亏损 ≈ ${Math.round(config.initial_balance*config.position_pct/100)}×{config.leverage}×{config.custom_stoploss}% = ${Math.round(config.initial_balance*config.position_pct/100 * config.leverage * config.custom_stoploss / 100)}</div>
        </div>
        <div className="flex items-end">
          <button
            className="w-full bg-blue-600 hover:bg-blue-700 text-white rounded px-3 py-1.5 text-sm disabled:opacity-50"
            onClick={onRun}
            disabled={running}
          >
            {running ? '回测中...' : '▶ 运行回测'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Metrics Panel ────────────────────────────────────────────────────────

function MetricsPanel({ m }: { m: Metrics }) {
  const items = [
    { label: '总交易', value: m.total_trades, color: '' },
    { label: '总盈亏', value: pct(m.total_profit_pct), color: m.total_profit_pct >= 0 ? 'text-green-500' : 'text-red-500' },
    { label: '盈亏 USDT', value: usdt(m.total_profit_usdt), color: m.total_profit_usdt >= 0 ? 'text-green-500' : 'text-red-500' },
    { label: '胜率', value: `${fmt(m.win_rate)}%`, color: m.win_rate > 50 ? 'text-green-500' : 'text-red-500' },
    { label: '夏普比率', value: fmt(m.sharpe_ratio), color: m.sharpe_ratio > 1 ? 'text-green-500' : m.sharpe_ratio > 0 ? 'text-yellow-500' : 'text-red-500' },
    { label: '最大回撤', value: `${fmt(m.max_drawdown_pct)}%`, color: 'text-red-500' },
    { label: '平均盈亏', value: pct(m.avg_profit_pct), color: m.avg_profit_pct >= 0 ? 'text-green-500' : 'text-red-500' },
    { label: '最终余额', value: `$${fmt(m.final_balance)}`, color: m.final_balance >= m.starting_balance ? 'text-green-500' : 'text-red-500' },
  ]
  return (
    <div className="grid grid-cols-4 gap-2">
      {items.map((item, i) => (
        <div key={i} className="bg-gray-50 rounded-lg p-2.5">
          <div className="text-xs text-gray-500">{item.label}</div>
          <div className={`text-lg font-bold ${item.color}`}>{item.value}</div>
        </div>
      ))}
    </div>
  )
}

// ─── K-Line Chart ─────────────────────────────────────────────────────────

function KlineChart({ data, trades, selectedTime, onChartReady, dark }: {
  data: KlineData[]; trades: TradeRecord[];
  selectedTime?: number; onChartReady?: (chart: any) => void; dark?: boolean
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null)

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: dark ? '#1e293b' : '#ffffff' },
        textColor: dark ? '#e2e8f0' : '#333',
      },
      grid: {
        vertLines: { color: dark ? '#334155' : '#f0f0f0' },
        horzLines: { color: dark ? '#334155' : '#f0f0f0' },
      },
      width: containerRef.current.clientWidth,
      height: 400,
      crosshair: { mode: 0 },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    })

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderDownColor: '#ef4444',
      borderUpColor: '#22c55e',
      wickDownColor: '#ef4444',
      wickUpColor: '#22c55e',
    })

    chartRef.current = chart
    onChartReady?.(chart)

    // Set data
    series.setData(data.map(d => ({
      time: d.time as any,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    })))

    // Set markers for trades (buy=▲ green, sell=▼ red)
    if (trades.length > 0) {
      const markers = trades.map(t => {
        const isEntry = t.type === 'entry'
        const isLong = t.side === 'long'
        return {
          time: Math.floor(new Date(t.timestamp).getTime() / 1000) as any,
          position: (isEntry ? (isLong ? 'belowBar' : 'aboveBar') : (isLong ? 'aboveBar' : 'belowBar')) as 'belowBar' | 'aboveBar',
          color: isLong ? '#22c55e' : '#ef4444',
          shape: (isEntry ? (isLong ? 'arrowUp' : 'arrowDown') : (isLong ? 'arrowDown' : 'arrowUp')) as any,
          text: isEntry ? (isLong ? 'B' : 'S') : (isLong ? 'X' : 'X'),
          price: t.price,
        }
      })
      createSeriesMarkers(series, markers)
    }

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartRef.current = null
    }
  }, [data, trades])

  // Jump to selected trade
  useEffect(() => {
    if (selectedTime && chartRef.current) {
      const from = selectedTime - 86400 * 3  // 3天前
      const to = selectedTime + 86400 * 1     // 1天后
      chartRef.current.timeScale().setVisibleRange({ from: from as any, to: to as any })
    }
  }, [selectedTime])

  return <div ref={containerRef} className="w-full h-[400px]" />
}

// ─── Equity Curve Chart ───────────────────────────────────────────────────

function EquityChart({ curve, initBalance, dark }: { curve: { timestamp: string; equity: number }[]; initBalance: number; dark?: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || curve.length === 0) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: dark ? '#1e293b' : '#ffffff' },
        textColor: dark ? '#e2e8f0' : '#333',
      },
      grid: {
        vertLines: { color: dark ? '#334155' : '#f0f0f0' },
        horzLines: { color: dark ? '#334155' : '#f0f0f0' },
      },
      width: containerRef.current.clientWidth,
      height: 200,
      timeScale: { timeVisible: true },
      rightPriceScale: {
        scaleMargins: { top: 0.1, bottom: 0.2 },
      },
    })

    const series = chart.addSeries(LineSeries, {
      color: '#3b82f6',
      lineWidth: 2,
    })

    // Set data
    series.setData(curve.map(c => ({
      time: Math.floor(new Date(c.timestamp).getTime() / 1000) as any,
      value: c.equity,
    })))

    // Add baseline
    const baseLine = chart.addSeries(LineSeries, {
      color: '#94a3b8',
      lineWidth: 1,
      lineStyle: 2,
    })
    baseLine.setData([
      { time: Math.floor(new Date(curve[0].timestamp).getTime() / 1000) as any, value: initBalance },
      { time: Math.floor(new Date(curve[curve.length - 1].timestamp).getTime() / 1000) as any, value: initBalance },
    ])

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [curve, initBalance])

  return <div ref={containerRef} className="w-full h-[200px]" />
}

// ─── Trade Table ──────────────────────────────────────────────────────────

function TradeTable({ trades, onSelectTime }: { trades: TradeRecord[]; onSelectTime?: (ts: number) => void }) {
  const exits = trades.filter(t => t.type === 'exit').reverse()

  if (exits.length === 0) return <div className="text-gray-400 text-sm py-4 text-center">暂无交易记录</div>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1 pr-2">时间</th>
            <th className="text-left py-1 pr-2">交易对</th>
            <th className="text-left py-1 pr-2">方向</th>
            <th className="text-right py-1 pr-2">开仓价</th>
            <th className="text-right py-1 pr-2">平仓价</th>
            <th className="text-right py-1 pr-2">PnL</th>
            <th className="text-right py-1 pr-2">PnL%</th>
            <th className="text-left py-1 pr-2">依据</th>
            <th className="text-left py-1 pr-2">出场</th>
            <th className="text-right py-1 pr-2">费用</th>
          </tr>
        </thead>
        <tbody>
          {exits.map((t, i) => {
            // 按顺序匹配 entry（同pair+同side的entry按顺序对应exit）
            const prevEntries = trades.filter(e => e.type === 'entry' && e.pair === t.pair && e.side === t.side)
            const prevExits = trades.filter(e => e.type === 'exit' && e.pair === t.pair && e.side === t.side)
            const entryIdx = prevExits.indexOf(t)
            const entry = entryIdx >= 0 && entryIdx < prevEntries.length ? prevEntries[entryIdx] : undefined
            return (
              <tr key={i} className="border-b border-gray-100 hover:bg-gray-100 cursor-pointer"
                onClick={() => {
                  const ts = entry?.timestamp || t.timestamp
                  if (ts && onSelectTime) onSelectTime(new Date(ts).getTime() / 1000)
                  // 显示详情弹窗
                  const detail = document.getElementById('trade-detail')
                  if (detail) {
                    const entryFee = entry?.fee || 0
                    const exitFee = t.fee || 0
                    const totalFee = entryFee + exitFee
                    const invest = entry?.cost || 0
                    const lev = entry?.leverage || t.leverage || 1
                    const notional = invest * lev
                    const pnl = t.pnl || 0
                    const pnlPct = t.pnl_pct || 0
                    document.getElementById('td-pair')!.textContent = t.pair || ''
                    document.getElementById('td-side')!.textContent = entry?.side === 'long' ? '做多' : entry?.side === 'short' ? '做空' : '-'
                    document.getElementById('td-entry')!.textContent = entry?.price ? '$' + entry.price.toLocaleString() : '-'
                    document.getElementById('td-exit')!.textContent = t.price ? '$' + t.price.toLocaleString() : '-'
                    document.getElementById('td-pnl')!.textContent = (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2)
                    document.getElementById('td-pnl-pct')!.textContent = (pnlPct >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%'
                    document.getElementById('td-invest')!.textContent = '$' + invest.toFixed(2)
                    document.getElementById('td-leverage')!.textContent = lev + 'x'
                    document.getElementById('td-notional')!.textContent = '$' + notional.toFixed(2)
                    document.getElementById('td-entry-fee')!.textContent = '$' + entryFee.toFixed(4)
                    document.getElementById('td-exit-fee')!.textContent = '$' + exitFee.toFixed(4)
                    document.getElementById('td-total-fee')!.textContent = '$' + totalFee.toFixed(4)
                    document.getElementById('td-net-pnl')!.textContent = (pnl - totalFee >= 0 ? '+' : '') + '$' + (pnl - totalFee).toFixed(2)
                    document.getElementById('td-tag')!.textContent = entry?.enter_tag || '-'
                    document.getElementById('td-exit-reason')!.textContent = t.exit_reason || '-'
                    document.getElementById('td-duration')!.textContent = t.duration || '-'
                    document.getElementById('td-time')!.textContent = new Date(t.timestamp).toLocaleString()
                    detail.classList.remove('hidden')
                  }
                }}
              >
                <td className="py-1 pr-2">{new Date(t.timestamp).toLocaleDateString()}</td>
                <td className="py-1 pr-2">{t.pair?.split('/')[0]}</td>
                <td className={`py-1 pr-2 ${t.side === 'long' ? 'text-green-600' : 'text-red-600'}`}>
                  {t.side === 'long' ? '多' : '空'}
                </td>
                <td className="text-right py-1 pr-2">{entry ? fmt(entry.price, 1) : '-'}</td>
                <td className="text-right py-1 pr-2">{fmt(t.price, 1)}</td>
                <td className={`text-right py-1 pr-2 font-medium ${(t.pnl || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {usdt(t.pnl || 0)}
                </td>
                <td className={`text-right py-1 pr-2 ${(t.pnl_pct || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {pct(t.pnl_pct || 0)}
                </td>
                <td className="text-left py-1 pr-2 text-gray-400 text-[10px]">
                  {entry?.enter_tag || '-'}
                </td>
                <td className="text-left py-1 pr-2 text-[10px]">
                  <span className={t.exit_reason === '止损' ? 'text-red-500' : t.exit_reason === '止盈' || t.exit_reason === '移动止盈' ? 'text-green-500' : 'text-gray-400'}>
                    {t.exit_reason || '-'}
                  </span>
                </td>
                <td className="text-right py-1 pr-2 text-[10px] text-gray-400">
                  {t.fee ? '$' + t.fee.toFixed(3) : '-'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────

export default function Home() {
  const [dark, setDark] = useState(false)
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])
  const [config, setConfig] = useState({
    strategy: 'RealChanTheory',
    pairs: ['BTC/USDT:USDT', 'ETH/USDT:USDT'],
    timeframe: '1h',
    rangeDays: 0,
    initial_balance: 1000,
    stake_amount: 200,
    leverage: 3,
    fee: 0.04,
    max_open_trades: 3,
    slippage: 0.05,
    customStart: '20260101',
    customEnd: '20260520',
    position_pct: 25,
    custom_stoploss: 1.5,
  })

  const [klineData, setKlineData] = useState<KlineData[]>([])
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [selectedTradeTime, setSelectedTradeTime] = useState<number | undefined>(undefined)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'backtest' | 'editor' | 'library' | 'papertrade'>('backtest')
  const [strategyCode, setStrategyCode] = useState('')
  const [strategyList, setStrategyList] = useState<string[]>([])

  // Load strategy list
  useEffect(() => {
    fetch(`${API_BASE}/api/strategies`)
      .then(r => r.json())
      .then(d => setStrategyList(d.strategies.map((s: any) => s.name)))
      .catch(() => {})
  }, [])

  // Load default strategy code
  useEffect(() => {
    fetch(`${API_BASE}/api/strategies/${config.strategy}`)
      .then(r => r.json())
      .then(d => setStrategyCode(d.content))
      .catch(() => {})
  }, [config.strategy])

  // Load K-line data
  useEffect(() => {
    let limit = 500
    if (config.customStart && config.customEnd) {
      const s = new Date(+config.customStart.slice(0,4), +config.customStart.slice(4,6)-1, +config.customStart.slice(6,8))
      const e = new Date(+config.customEnd.slice(0,4), +config.customEnd.slice(4,6)-1, +config.customEnd.slice(6,8))
      const d = Math.ceil((e.getTime() - s.getTime()) / 86400000)
      limit = Math.max(d * 24, 100)
    }
    fetch(`${API_BASE}/api/data?pair=${config.pairs[0]}&timeframe=${config.timeframe}&limit=${limit}`)
      .then(r => r.json())
      .then(d => setKlineData(d.data || []))
      .catch(() => {})
  }, [config.pairs, config.timeframe, config.customStart, config.customEnd])

  const runBacktest = useCallback(async () => {
    setRunning(true)
    setError('')
    try {
      const timerange = config.customStart && config.customEnd
        ? `${config.customStart}-${config.customEnd}`
        : getTimerange(config.rangeDays || 30)
      const pairs = config.pairs
      const res = await fetch(`${API_BASE}/api/backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategy: config.strategy,
          pairs,
          timeframe: config.timeframe,
          timerange,
          stake_amount: config.stake_amount,
          initial_balance: config.initial_balance,
          max_open_trades: config.max_open_trades,
          leverage: config.leverage,
          fee: config.fee / 100,
          slippage: config.slippage / 100,
          position_pct: config.position_pct,
          custom_stoploss: config.custom_stoploss,
          trading_mode: 'futures',
        }),
      })
      const data = await res.json()
      if (!res.ok || data.success === false) {
        setError(data.detail || data.error || '回测失败')
      } else {
        setResult(data)
      }
    } catch (e: any) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }, [config])

  const saveStrategy = useCallback(async () => {
    await fetch(`${API_BASE}/api/strategies/${config.strategy}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: strategyCode }),
    })
    alert('策略已保存')
  }, [config.strategy, strategyCode])

  return (
    <div className="min-h-screen" style={{background:'var(--bg-page)'}}>
      {/* Header */}
      <header className="border-b px-4 py-3 flex items-center justify-between sticky top-0 z-10" style={{background:'var(--bg-header)', borderColor:'var(--border-default)'}}>
        <h1 className="text-lg font-bold bg-gradient-to-r from-blue-600 to-purple-600 text-transparent bg-clip-text">📊 策略回测系统</h1>
        <div className="flex items-center gap-2">
          <button className="text-lg opacity-60 hover:opacity-100 transition-opacity" onClick={() => setDark(!dark)} title="切换主题">
            {dark ? '☀️' : '🌙'}
          </button>
        </div>
        <div className="flex gap-0.5 bg-gray-100 dark:bg-gray-700 rounded-lg p-0.5">
          <button
            className={`px-3 py-1.5 text-sm rounded-md font-medium transition-all ${activeTab === 'backtest' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
            onClick={() => setActiveTab('backtest')}
          >📈 回测</button>
          <button
            className={`px-3 py-1.5 text-sm rounded-md font-medium transition-all ${activeTab === 'editor' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
            onClick={() => setActiveTab('editor')}
          >✏️ 策略</button>
          <button
            className={`px-3 py-1.5 text-sm rounded-md font-medium transition-all ${activeTab === 'library' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
            onClick={() => setActiveTab('library')}
          >📚 策略库</button>
          <button
            className={`px-3 py-1.5 text-sm rounded-md font-medium transition-all ${activeTab === 'papertrade' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
            onClick={() => setActiveTab('papertrade')}
          >🟢 模拟盘</button>
        </div>
      </header>

      <div className="p-4 max-w-7xl mx-auto">
        {activeTab === 'backtest' && (
          <div className="grid grid-cols-12 gap-4">
            {/* Left: Config */}
            <div className="col-span-12 lg:col-span-3">
              <div className="border rounded-lg p-3">
                <h2 className="text-sm font-semibold mb-2">回测参数</h2>
                <ConfigPanel
                  config={config}
                  onChange={updates => setConfig(prev => ({ ...prev, ...updates }))}
                  onRun={runBacktest}
                  running={running}
                  strategyList={strategyList}
                />
                {error && <div className="text-red-500 text-xs mt-2">{error}</div>}
              </div>

              {/* Quick Strategy Stats */}
              {result && result.config && (
                <div className="border rounded-lg p-3 mt-3">
                  <h2 className="text-sm font-semibold mb-2">策略配置</h2>
                  <div className="text-xs space-y-1 text-gray-600">
                    <div>策略: {result.config.strategy}</div>
                    <div>交易对: {result.config.pairs?.join(', ')}</div>
                    <div>粒度: {result.config.timeframe}</div>
                    <div>杠杆: {result.config.leverage}x</div>
                    <div>费率: {result.config.fee * 100}%</div>
                  </div>
                </div>
              )}
            </div>

            {/* Right: Charts & Results */}
            <div className="col-span-12 lg:col-span-9 space-y-3">
              {/* K-Line Chart */}
              <div className="border rounded-lg p-2">
                <KlineChart data={klineData} trades={result?.trades || []}
                  selectedTime={selectedTradeTime} dark={dark} />
              </div>

              {/* Metrics */}
              {result && (
                <div className="border rounded-lg p-3">
                  <h2 className="text-sm font-semibold mb-2">回测指标</h2>
                  <MetricsPanel m={result.metrics} />
                </div>
              )}

              {/* Equity Curve */}
              {result && result.equity_curve && result.equity_curve.length > 0 && (
                <div className="border rounded-lg p-2">
                  <h2 className="text-sm font-semibold mb-2 px-1">资金曲线</h2>
                  <EquityChart curve={result.equity_curve} initBalance={result.config.initial_balance} dark={dark} />
                </div>
              )}

              {/* Trade Table */}
              {result && (
                <div className="border rounded-lg p-3">
                  <h2 className="text-sm font-semibold mb-2">
                    交易明细 ({(result.trades || []).filter((t: any) => t.type === 'exit').length} 笔平仓)
                  </h2>
                  <TradeTable trades={result.trades || []} onSelectTime={setSelectedTradeTime} />
                </div>
              )}
            </div>
          </div>
        )}

        {/* 交易明细弹窗 */}
        <div id="trade-detail" className="hidden fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={e => { if (e.target === e.currentTarget) document.getElementById('trade-detail')?.classList.add('hidden') }}>
          <div className="bg-white rounded-2xl p-5 max-w-sm w-full mx-4 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-sm">交易详情</h3>
              <button className="text-gray-400 hover:text-gray-600 text-lg leading-none" onClick={() => document.getElementById('trade-detail')?.classList.add('hidden')}>✕</button>
            </div>
            <div className="space-y-2 text-xs">
              <div className="grid grid-cols-2 gap-2 bg-gray-50 rounded-lg p-3">
                <div><span className="text-gray-400">交易对</span><br/><strong id="td-pair">-</strong></div>
                <div><span className="text-gray-400">方向</span><br/><strong id="td-side">-</strong></div>
                <div><span className="text-gray-400">开仓价</span><br/><strong id="td-entry">-</strong></div>
                <div><span className="text-gray-400">平仓价</span><br/><strong id="td-exit">-</strong></div>
                <div><span className="text-gray-400">盈亏</span><br/><strong id="td-pnl" className="font-bold">-</strong></div>
                <div><span className="text-gray-400">盈亏%</span><br/><strong id="td-pnl-pct">-</strong></div>
              </div>
              <div className="grid grid-cols-3 gap-2 rounded-lg p-3 border">
                <div><span className="text-gray-400">投入</span><br/><span id="td-invest">-</span></div>
                <div><span className="text-gray-400">杠杆</span><br/><span id="td-leverage">-</span></div>
                <div><span className="text-gray-400">名义价值</span><br/><span id="td-notional">-</span></div>
              </div>
              <div className="rounded-lg p-3 border">
                <div className="text-gray-400 mb-1">手续费</div>
                <div className="grid grid-cols-3 gap-2">
                  <div>入场 <span id="td-entry-fee" className="text-red-500">-</span></div>
                  <div>出场 <span id="td-exit-fee" className="text-red-500">-</span></div>
                  <div>合计 <span id="td-total-fee" className="text-red-500 font-bold">-</span></div>
                </div>
              </div>
              <div className="rounded-lg p-3 border">
                <div className="grid grid-cols-2 gap-2">
                  <div><span className="text-gray-400">入场依据</span><br/><span id="td-tag" className="text-blue-600 text-[10px]">-</span></div>
                  <div><span className="text-gray-400">出场原因</span><br/><span id="td-exit-reason">-</span></div>
                  <div className="col-span-2"><span className="text-gray-400">持有时间</span><br/><span id="td-duration">-</span></div>
                  <div className="col-span-2"><span className="text-gray-400">成交时间</span><br/><span id="td-time" className="text-[10px]">-</span></div>
                </div>
              </div>
              <div className="text-center pt-1">
                <span className="text-gray-400">净盈亏(扣费后): </span>
                <strong id="td-net-pnl" className="text-base">-</strong>
              </div>
            </div>
          </div>
        </div>

        {activeTab === 'editor' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">策略编辑器</h2>
              <div className="flex gap-2">
                <select className="text-sm border rounded px-2 py-1"
                  value={config.strategy}
                  onChange={e => {
                    setConfig(prev => ({ ...prev, strategy: e.target.value }))
                    fetch(`${API_BASE}/api/strategies/${e.target.value}`)
                      .then(r => r.json())
                      .then(d => setStrategyCode(d.content))
                  }}
                >
                  {strategyList.map(s => <option key={s}>{s}</option>)}
                </select>
                <button className="bg-blue-600 text-white text-sm px-3 py-1 rounded" onClick={saveStrategy}>
                  保存
                </button>
              </div>
            </div>
            <textarea
              className="w-full h-[600px] font-mono text-xs border rounded p-3"
              value={strategyCode}
              onChange={e => setStrategyCode(e.target.value)}
            />
          </div>
        )}

        {activeTab === 'library' && (
          <StrategyLibrary onSelect={(name) => {
            setConfig(prev => ({ ...prev, strategy: name }))
            fetch(`${API_BASE}/api/strategies/${name}`)
              .then(r => r.json())
              .then(d => setStrategyCode(d.content))
            setActiveTab('editor')
          }} />
        )}

        {activeTab === 'papertrade' && (
          <PaperTradePanel API_BASE={API_BASE} />
        )}
      </div>
    </div>
  )
}

// ─── Strategy Library ─────────────────────────────────────────────────────

const STRATEGIES = [
  {
    name: 'RealChanTheory',
    title: '🏆 真正缠论',
    description: '缠论+EMA50趋势+ATR波动率过滤。365天BTC:39笔|胜率51%|收益+8.9%|夏普1.30|回撤7.3%。纯顺势交易，不抄底不摸顶。推荐做市费率+BTC单币。',
    tags: ['缠论', '🏆推荐', '低回撤'],
    params: { timeframe: '1h', leverage: '3x', fee: '0.02%' },
    perf: '+16.16%',
    risk: '低',
  },
  {
    name: 'ChanTheoryStrategy',
    title: '缠论三买/三卖',
    description: '经典缠论三买三卖。96根K线中枢+MACD过滤。15m 41%胜率。适合偏好15m周期的短线交易者。',
    tags: ['缠论', '短线'],
    params: { timeframe: '15m', leverage: '5x' },
    perf: '+14.91%',
    risk: '中',
  },
  {
    name: 'ZScorePro',
    title: 'Z-Score PRO',
    description: 'Z-Score统计均值回归。5m周期高频交易，51%胜率。需10x杠杆+做市费率。适合追求高频交易的用户。',
    tags: ['短线', '统计', '高频'],
    params: { timeframe: '5m', leverage: '10x', fee: '0.02%' },
    perf: '+27%',
    risk: '高',
  },
  {
    name: 'ZScoreReversionStrategy',
    title: 'Z-Score 标准版',
    description: 'Z-Score均值回归标准版。5m周期，无需做市费率。胜率51%，回撤低，适合保守型用户。',
    tags: ['短线', '统计', '保守'],
    params: { timeframe: '5m', leverage: '3x' },
    perf: '+0.05%',
    risk: '低',
  },
  {
    name: 'BollingerStrategy',
    title: '布林带均值回归',
    description: '经典布林带+RSI。价格触及下轨做多、上轨做空。1h周期，震荡行情有效。',
    tags: ['均值回归', '震荡'],
    params: { timeframe: '1h' },
    perf: '中',
    risk: '中',
  },
  {
    name: 'SupertrendStrategy',
    title: 'Supertrend 趋势',
    description: '基于ATR的超级趋势指标。纯趋势跟踪，1h周期。趋势行情中表现优异。',
    tags: ['趋势跟踪', 'ATR'],
    params: { timeframe: '1h' },
    perf: '中',
    risk: '中',
  },
  {
    name: 'VwapReversionStrategy',
    title: 'VWAP 均值回归',
    description: '机构级VWAP策略。5m周期，胜率51%。价格偏离VWAP时入场，回归出场。',
    tags: ['短线', 'VWAP'],
    params: { timeframe: '5m' },
    perf: '+0.05%',
    risk: '低',
  },
  {
    name: 'AIStrategy',
    title: 'AI 增强策略',
    description: '调用OpenAI/Claude API辅助信号判断。需API Key。适合想尝试AI交易的用户。',
    tags: ['AI', 'LLM'],
    params: { provider: 'openai/claude' },
    perf: '需API',
    risk: '中',
  },
]

function StrategyLibrary({ onSelect }: { onSelect: (name: string) => void }) {
  const [search, setSearch] = useState('')
  const [selectedTag, setSelectedTag] = useState<string>('')

  const allTags = Array.from(new Set(STRATEGIES.flatMap(s => s.tags)))
  const filtered = STRATEGIES.filter(s => {
    if (search && !s.name.toLowerCase().includes(search.toLowerCase()) && !s.title.includes(search)) return false
    if (selectedTag && !s.tags.includes(selectedTag)) return false
    return true
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <input
          className="flex-1 border rounded px-3 py-1.5 text-sm"
          placeholder="搜索策略..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <div className="flex gap-1 flex-wrap">
          <button
            className={`text-xs px-2 py-1 rounded ${!selectedTag ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600'}`}
            onClick={() => setSelectedTag('')}
          >全部</button>
          {allTags.map(tag => (
            <button
              key={tag}
              className={`text-xs px-2 py-1 rounded ${selectedTag === tag ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600'}`}
              onClick={() => setSelectedTag(selectedTag === tag ? '' : tag)}
            >{tag}</button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {filtered.map(s => {
          const riskColor = s.risk === '低' ? 'text-green-600' : s.risk === '中' ? 'text-yellow-600' : 'text-red-600'
          return (
          <div key={s.name} className="strategy-card border rounded-xl p-4 bg-white">
            <div className="flex items-start justify-between mb-2">
              <div>
                <h3 className="font-semibold text-sm">{s.title}</h3>
                <code className="text-[11px] text-gray-400">{s.name}.py</code>
              </div>
              <button
                className="text-xs bg-blue-600 text-white px-3 py-1.5 rounded-lg hover:bg-blue-700 font-medium transition-colors"
                onClick={() => onSelect(s.name)}
              >使用</button>
            </div>
            <p className="text-xs text-gray-500 mb-3 leading-relaxed">{s.description}</p>
            <div className="flex flex-wrap gap-1 mb-2">
              {s.tags.map(t => (
                <span key={t} className="tag">{t}</span>
              ))}
            </div>
            <div className="flex items-center gap-3 text-xs border-t pt-2 text-gray-400">
              <span>收益 <strong className={s.perf.startsWith('+') ? 'text-green-600' : ''}>{s.perf}</strong></span>
              <span className={riskColor}>风险 {s.risk}</span>
              <span>⏱ {s.params.timeframe || '1h'}</span>
            </div>
          </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── 模拟盘面板 ──────────────────────────────────────────────────────────

function PaperTradePanel({ API_BASE }: { API_BASE: string }) {
  const [status, setStatus] = useState<any>(null)
  const [running, setRunning] = useState(false)
  const [loading, setLoading] = useState(false)
  const [strategy, setStrategy] = useState('RealChanTheory')
  const [strategyList, setStrategyList] = useState<string[]>([])
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<any>(null)

  // 加载策略列表
  useEffect(() => {
    fetch(`${API_BASE}/api/strategies`)
      .then(r => r.json())
      .then(d => setStrategyList((d.strategies || []).map((s: any) => s.name)))
      .catch(() => {})
  }, [API_BASE])

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/papertrade/status`)
      const d = await r.json()
      setStatus(d)
      setRunning(d.running)
    } catch {}
  }, [API_BASE])

  useEffect(() => {
    if (running) {
      const timer = setInterval(fetchStatus, 5000)
      return () => clearInterval(timer)
    }
  }, [running, fetchStatus])

  // 进场时拉一次状态
  useEffect(() => { fetchStatus() }, [fetchStatus])

  const handleStart = async () => {
    setLoading(true)
    try {
      await fetch(`${API_BASE}/api/papertrade/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy }),
      })
      await new Promise(r => setTimeout(r, 5000))
      await fetchStatus()
    } catch {}
    setLoading(false)
  }

  const handleStop = async () => {
    await fetch(`${API_BASE}/api/papertrade/stop`, { method: 'POST' })
    setRunning(false)
    await fetchStatus()
  }

  // ── 权益曲线（使用静态 createChart） ──
  useEffect(() => {
    if (!chartRef.current || !status?.equity_curve?.length) return
    if (chartInstance.current) { chartInstance.current.remove(); chartInstance.current = null }
    try {
      const chart = createChart(chartRef.current, {
        width: chartRef.current.clientWidth,
        height: 280,
        layout: { background: { color: 'transparent' }, textColor: '#888' },
        grid: { vertLines: { color: '#eee' }, horzLines: { color: '#eee' } },
        timeScale: { visible: false },
        crosshair: { vertLine: { visible: false }, horzLine: { visible: false } },
      })
      const line = chart.addLineSeries({ color: '#3b82f6', lineWidth: 2 })
      const data = status.equity_curve.map((p: any) => ({
        time: new Date(p.timestamp).getTime() / 1000,
        value: p.equity,
      }))
      line.setData(data)
      chart.timeScale().fitContent()
      chartInstance.current = chart
    } catch {}
    return () => { if (chartInstance.current) { chartInstance.current.remove(); chartInstance.current = null } }
  }, [status?.equity_curve])

  const paired = status?.paired_trades || []
  const signals = status?.recent_signals || []
  const totalPnl = paired.reduce((s: number, t: any) => s + (t.pnl || 0), 0)
  const wins2 = paired.filter((t: any) => (t.pnl || 0) > 0).length
  const winPnl = paired.filter((t: any) => t.pnl > 0).map((t: any) => t.pnl)
  const losePnl = paired.filter((t: any) => t.pnl < 0).map((t: any) => t.pnl)
  const avgWin = winPnl.length ? winPnl.reduce((a: number,b: number) => a+b, 0) / winPnl.length : 0
  const avgLoss = losePnl.length ? Math.abs(losePnl.reduce((a: number,b: number) => a+b, 0) / losePnl.length) : 0
  const pf = avgLoss > 0 ? (avgWin / avgLoss) * (wins2 / Math.max(1, paired.length - wins2)) : 0
  const best = paired.length ? paired.reduce((a: any, b: any) => a.pnl > b.pnl ? a : b) : null
  const worst = paired.length ? paired.reduce((a: any, b: any) => a.pnl < b.pnl ? a : b) : null
  const bal = status?.equity || 1000
  const pnlColor = totalPnl >= 0 ? 'text-green-500' : 'text-red-500'

  return (
    <div className="space-y-4">

      {/* 策略选择 + 控制栏 */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          className="border rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800"
          value={strategy}
          onChange={e => setStrategy(e.target.value)}
          disabled={running}
        >
          {strategyList.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <button
          className={`px-4 py-2 text-sm rounded-lg font-medium transition-all ${running ? 'bg-gray-300 text-gray-500 cursor-not-allowed' : 'bg-green-600 text-white hover:bg-green-700'}`}
          onClick={handleStart} disabled={running || loading}
        >{loading ? '启动中...' : '▶ 启动'}</button>
        <button
          className={`px-4 py-2 text-sm rounded-lg font-medium transition-all ${!running ? 'bg-gray-300 text-gray-500 cursor-not-allowed' : 'bg-red-600 text-white hover:bg-red-700'}`}
          onClick={handleStop} disabled={!running}
        >⏹ 停止</button>
        <button className="px-4 py-2 text-sm rounded-lg font-medium bg-gray-100 hover:bg-gray-200 transition-colors" onClick={fetchStatus}>🔄 刷新</button>
        {!running && paired.length === 0 && (
          <span className="text-xs text-gray-400">选择策略 → 点「启动」</span>
        )}
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
        <div className="border rounded-lg p-2.5"><div className="text-xs text-gray-400">状态</div><div className="text-base font-bold">{running ? '🟢 运行' : '🔴 停止'}</div></div>
        <div className="border rounded-lg p-2.5"><div className="text-xs text-gray-400">权益</div><div className="text-base font-bold">${bal.toFixed(0)}</div></div>
        <div className="border rounded-lg p-2.5"><div className="text-xs text-gray-400">总盈亏</div><div className={`text-base font-bold ${pnlColor}`}>{totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(2)}</div></div>
        <div className="border rounded-lg p-2.5"><div className="text-xs text-gray-400">胜率</div><div className="text-base font-bold">{paired.length > 0 ? `${(wins2/paired.length*100).toFixed(0)}%` : '—'}</div></div>
        <div className="border rounded-lg p-2.5"><div className="text-xs text-gray-400">盈亏比</div><div className="text-base font-bold">{pf !== null ? pf.toFixed(2) : '—'}</div></div>
        <div className="border rounded-lg p-2.5"><div className="text-xs text-gray-400">均盈/均亏</div><div className="text-base font-bold text-xs">{avgWin ? `+${avgWin.toFixed(2)}` : '—'}/{avgLoss ? avgLoss.toFixed(2) : '—'}</div></div>
        <div className="border rounded-lg p-2.5"><div className="text-xs text-gray-400">交易</div><div className="text-base font-bold">{paired.length}笔</div></div>
      </div>

      {/* 权益曲线 */}
      {status?.equity_curve?.length > 0 && (
        <div className="border rounded-lg p-3">
          <h3 className="text-sm font-semibold mb-2">权益曲线</h3>
          <div ref={chartRef} className="w-full" style={{ height: 240 }} />
        </div>
      )}

      {/* 信号分组统计 */}
      {paired.length > 0 && (() => {
        const byTag: Record<string, {pnls:number[], wins:number}> = {}
        paired.forEach((t: any) => {
          const tag = (t.enter_tag || '?').slice(0,4)
          if (!byTag[tag]) byTag[tag] = {pnls:[], wins:0}
          byTag[tag].pnls.push(t.pnl)
          if (t.pnl > 0) byTag[tag].wins++
        })
        return (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {Object.entries(byTag).map(([tag, data]: [string, any]) => (
              <div key={tag} className="border rounded-lg p-2.5 text-xs">
                <div className="font-semibold mb-1">{tag}</div>
                <div className="text-gray-500">{data.pnls.length}笔 胜率{(data.wins/data.pnls.length*100).toFixed(0)}%</div>
                <div className={`font-medium ${data.pnls.reduce((a:number,b:number)=>a+b,0) > 0 ? 'text-green-600' : 'text-red-600'}`}>
                  合计{data.pnls.reduce((a:number,b:number)=>a+b,0).toFixed(2)}
                </div>
              </div>
            ))}
          </div>
        )
      })()}

      {/* 当前持仓 */}
      {status?.positions?.length > 0 && (
        <div className="border rounded-lg p-3">
          <h3 className="text-sm font-semibold mb-2">当前持仓</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="border-b text-left"><th className="py-1 pr-3">交易对</th><th className="py-1 pr-3">方向</th><th className="py-1 pr-3">入场价</th><th className="py-1 pr-3">数量</th><th className="py-1 pr-3">入场时间</th><th className="py-1 pr-3">标记</th></tr></thead>
              <tbody>{status.positions.map((p: any, i: number) => (
                <tr key={i} className="border-b"><td className="py-1 pr-3">{p.pair?.split('/')[0]}</td><td className="py-1 pr-3">{p.side === 'long' ? '🟢 多' : '🔴 空'}</td><td className="py-1 pr-3">${p.entry_price}</td><td className="py-1 pr-3">{p.size}</td><td className="py-1 pr-3 text-xs">{p.entry_time?.slice(0,16)}</td><td className="py-1 pr-3 text-gray-400">{p.enter_tag?.slice(0,15)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}

      {/* 配对交易卡片 */}
      {paired.length > 0 && (
        <div className="border rounded-lg p-3">
          <h3 className="text-sm font-semibold mb-3">交易记录 ({paired.length} 笔)</h3>
          <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
            {paired.slice().reverse().map((t: any, i: number) => (
              <div key={i} className={`border rounded-lg p-3 flex items-stretch gap-3 ${t.pnl > 0 ? 'border-l-4 border-l-green-500' : 'border-l-4 border-l-red-500'}`}>
                {/* 左侧：方向+盈亏 */}
                <div className="flex flex-col items-center justify-center min-w-[70px]">
                  <div className={`text-lg ${t.direction === 'long' ? 'text-green-600' : 'text-red-600'}`}>
                    {t.direction === 'long' ? '🟢' : '🔴'}
                  </div>
                  <div className={`text-base font-bold ${t.pnl > 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {t.pnl > 0 ? '+' : ''}{t.pnl.toFixed(2)}
                  </div>
                  <div className={`text-xs ${t.pnl > 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {t.pnl_pct > 0 ? '+' : ''}{t.pnl_pct}%
                  </div>
                </div>
                {/* 中间：价格+时间 */}
                <div className="flex-1 text-xs space-y-0.5">
                  <div className="flex items-center gap-3">
                    <span className="font-medium">{t.pair?.split('/')[0]}</span>
                    <span className="text-gray-400">{t.enter_tag}</span>
                    <span className="text-gray-400">{t.duration}</span>
                  </div>
                  <div className="text-gray-500">
                    入 {t.entry_price} → 出 {t.exit_price}
                  </div>
                  <div className="text-gray-400">
                    {t.entry_time?.slice(5)} → {t.exit_time?.slice(5)}
                  </div>
                </div>
                {/* 右侧：出场原因 */}
                <div className="flex flex-col items-end justify-center min-w-[60px] text-xs">
                  <span className={`px-2 py-0.5 rounded font-medium ${
                    t.exit_reason?.includes('止盈') ? 'bg-green-100 text-green-700' :
                    t.exit_reason?.includes('止损') ? 'bg-red-100 text-red-700' :
                    t.exit_reason?.includes('结构') ? 'bg-blue-100 text-blue-700' :
                    t.exit_reason?.includes('移动') ? 'bg-yellow-100 text-yellow-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>{t.exit_reason}</span>
                  <div className={`text-xs mt-1 font-medium ${t.cumulative_pnl > 0 ? 'text-green-600' : 'text-red-600'}`}>
                    累计 {t.cumulative_pnl > 0 ? '+' : ''}{t.cumulative_pnl.toFixed(2)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 最佳/最差交易 */}
      {best && worst && paired.length > 1 && (
        <div className="grid grid-cols-2 gap-3">
          {best && (
            <div className="border rounded-lg p-3 border-green-200">
              <div className="text-xs text-gray-400 mb-1">🏆 最佳交易</div>
              <div className="text-sm font-bold text-green-600">+{best.pnl.toFixed(2)}</div>
              <div className="text-xs text-gray-500">{best.pair?.split('/')[0]} {best.enter_tag} {best.duration}</div>
            </div>
          )}
          {worst && (
            <div className="border rounded-lg p-3 border-red-200">
              <div className="text-xs text-gray-400 mb-1">💀 最差交易</div>
              <div className="text-sm font-bold text-red-600">{worst.pnl.toFixed(2)}</div>
              <div className="text-xs text-gray-500">{worst.pair?.split('/')[0]} {worst.enter_tag} {worst.duration}</div>
            </div>
          )}
        </div>
      )}

      {/* 空状态 */}
      {!running && paired.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          <div className="text-4xl mb-3">📊</div>
          <p className="text-sm">模拟盘未运行</p>
          <p className="text-xs mt-1">选择策略 → 点击「启动」开始模拟交易</p>
        </div>
      )}
    </div>
  )
}
