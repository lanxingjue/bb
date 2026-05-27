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
  { label: '自定义', value: '' },
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
            {strategyList.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500">交易对</label>
          <select className="w-full text-sm border rounded px-2 py-1"
            value={config.pair}
            onChange={e => onChange({ pair: e.target.value })}
          >
            {PAIRS.map(p => <option key={p}>{p}</option>)}
          </select>
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
          <select className="w-full text-sm border rounded px-2 py-1"
            value={config.rangeDays}
            onChange={e => onChange({ rangeDays: Number(e.target.value) })}
          >
            {RANGES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
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

function KlineChart({ data, trades }: { data: KlineData[]; trades: TradeRecord[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null)

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#333',
      },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
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

    // Set data
    series.setData(data.map(d => ({
      time: d.time as any,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    })))

    // Set markers for trades
    if (trades.length > 0) {
      const markers = trades
        .filter(t => t.type === 'entry')
        .map(t => ({
          time: Math.floor(new Date(t.timestamp).getTime() / 1000) as any,
          position: t.side === 'long' ? 'belowBar' as const : 'aboveBar' as const,
          color: t.side === 'long' ? '#22c55e' : '#ef4444',
          shape: t.side === 'long' ? 'arrowUp' as const : 'arrowDown' as const,
          text: t.side === 'long' ? 'B' : 'S',
        }))
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

  return <div ref={containerRef} className="w-full h-[400px]" />
}

// ─── Equity Curve Chart ───────────────────────────────────────────────────

function EquityChart({ curve, initBalance }: { curve: { timestamp: string; equity: number }[]; initBalance: number }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || curve.length === 0) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#333',
      },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
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

function TradeTable({ trades }: { trades: TradeRecord[] }) {
  const exits = trades.filter(t => t.type === 'exit').slice(-50).reverse()

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
          </tr>
        </thead>
        <tbody>
          {exits.map((t, i) => {
            // Find matching entry
            const entry = trades.find(e => e.type === 'entry' && e.pair === t.pair && e.side === t.side)
            return (
              <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
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
  const [config, setConfig] = useState({
    strategy: 'TestStrategy',
    pair: 'BTC/USDT:USDT',
    timeframe: '1h',
    rangeDays: 30,
    initial_balance: 1000,
    stake_amount: 100,
    leverage: 1,
    fee: 0.04,
    max_open_trades: 3,
    slippage: 0.05,
  })

  const [klineData, setKlineData] = useState<KlineData[]>([])
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'backtest' | 'editor' | 'library'>('backtest')
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
    const days = config.rangeDays || 30
    fetch(`${API_BASE}/api/data?pair=${config.pair}&timeframe=${config.timeframe}&limit=${days * 24}`)
      .then(r => r.json())
      .then(d => setKlineData(d.data || []))
      .catch(() => {})
  }, [config.pair, config.timeframe, config.rangeDays])

  const runBacktest = useCallback(async () => {
    setRunning(true)
    setError('')
    try {
      const timerange = getTimerange(config.rangeDays || 30)
      const pairs = [config.pair]
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
          trading_mode: 'futures',
        }),
      })
      const data = await res.json()
      if (data.success === false) {
        setError(data.error || '回测失败')
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
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b bg-gray-50 px-4 py-2 flex items-center justify-between">
        <h1 className="text-lg font-bold">策略回测系统</h1>
        <div className="flex gap-1">
          <button
            className={`px-3 py-1 text-sm rounded ${activeTab === 'backtest' ? 'bg-blue-600 text-white' : 'text-gray-600'}`}
            onClick={() => setActiveTab('backtest')}
          >回测</button>
          <button
            className={`px-3 py-1 text-sm rounded ${activeTab === 'editor' ? 'bg-blue-600 text-white' : 'text-gray-600'}`}
            onClick={() => setActiveTab('editor')}
          >策略</button>
          <button
            className={`px-3 py-1 text-sm rounded ${activeTab === 'library' ? 'bg-blue-600 text-white' : 'text-gray-600'}`}
            onClick={() => setActiveTab('library')}
          >策略库</button>
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
                <KlineChart data={klineData} trades={result?.trades || []} />
              </div>

              {/* Metrics */}
              {result && (
                <div className="border rounded-lg p-3">
                  <h2 className="text-sm font-semibold mb-2">回测指标</h2>
                  <MetricsPanel m={result.metrics} />
                </div>
              )}

              {/* Equity Curve */}
              {result && result.equity_curve.length > 0 && (
                <div className="border rounded-lg p-2">
                  <h2 className="text-sm font-semibold mb-2 px-1">资金曲线</h2>
                  <EquityChart curve={result.equity_curve} initBalance={result.config.initial_balance} />
                </div>
              )}

              {/* Trade Table */}
              {result && (
                <div className="border rounded-lg p-3">
                  <h2 className="text-sm font-semibold mb-2">
                    交易明细 ({result.trades.filter(t => t.type === 'exit').length} 笔平仓)
                  </h2>
                  <TradeTable trades={result.trades} />
                </div>
              )}
            </div>
          </div>
        )}

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
      </div>
    </div>
  )
}

// ─── Strategy Library ─────────────────────────────────────────────────────

const STRATEGIES = [
  {
    name: 'MacdStrategy',
    title: 'MACD 金叉死叉',
    description: '经典 MACD 指标策略。MACD 线上穿信号线时做多（金叉），下穿时做空（死叉），配合 RSI 过滤假信号。趋势跟踪型，适合震荡偏趋势市场。',
    tags: ['趋势跟踪', 'MACD', 'RSI'],
    params: { timeframe: '1h', atr_period: 14 },
    perf: '中等',
    risk: '中',
  },
  {
    name: 'EmaCrossStrategy',
    title: 'EMA 双均线交叉',
    description: 'EMA9/21 金叉死叉 + EMA50 趋势过滤。只在多头趋势中做多（EMA21>EMA50），空头趋势中做空。适合有明显趋势的行情，震荡市会频繁假信号。',
    tags: ['趋势跟踪', '均线', 'EMA'],
    params: { timeframe: '1h', fast_ema: 9, slow_ema: 21 },
    perf: '较高',
    risk: '中',
  },
  {
    name: 'BollingerStrategy',
    title: '布林带均值回归',
    description: '价格触及布林带下轨 + RSI 超卖时做多，触及上轨 + RSI 超买时做空。属于均值回归策略，适合震荡行情，趋势行情中容易逆势亏损。',
    tags: ['均值回归', '布林带', '震荡'],
    params: { timeframe: '1h', bb_period: 20, bb_std: 2.0 },
    perf: '中',
    risk: '中高',
  },
  {
    name: 'SupertrendStrategy',
    title: 'Supertrend 超级趋势',
    description: '基于 ATR 的超级趋势指标。出现绿色反转信号做多，红色反转信号做空。纯趋势跟踪，胜率不高但盈亏比好，适合大趋势行情。',
    tags: ['趋势跟踪', 'ATR', 'Supertrend'],
    params: { timeframe: '1h', atr_period: 10, multiplier: 3.0 },
    perf: '较高',
    risk: '中',
  },
  {
    name: 'SampleStrategy',
    title: 'RSI + EMA 混合',
    description: 'RSI 超买超卖 + EMA 趋势确认。RSI<30 且 EMA 多头排列时做多，RSI>70 且 EMA 空头排列时做空。综合型策略，适应性强。',
    tags: ['综合', 'RSI', 'EMA'],
    params: { timeframe: '1h', rsi_period: 14 },
    perf: '中',
    risk: '低中',
  },
  {
    name: 'TestStrategy',
    title: 'RSI 简单策略',
    description: '纯 RSI 信号：RSI<35 做多，RSI>65 做空。不加过滤器，信号频繁，适合作为策略对比的基准线。',
    tags: ['简单', 'RSI', '基准'],
    params: { timeframe: '1h', buy_rsi: 35, sell_rsi: 65 },
    perf: '低',
    risk: '高',
  },
  {
    name: 'AIStrategy',
    title: 'AI 增强策略',
    description: '技术指标计算市场特征，调用 OpenAI/Claude API 辅助判断多空方向。AI 不可用时自动回退到纯技术指标。需要配置 API Key 才能启用 AI。',
    tags: ['AI', 'LLM', '混合'],
    params: { provider: 'openai/claude', model: 'gpt-4o-mini' },
    perf: '待测试',
    risk: '中',
  },
  // ── 短线/超短线策略 ──
  {
    name: 'CandlestickPatternStrategy',
    title: 'K 线形态短线',
    description: '基于 TA-Lib 识别看涨/看跌吞没、锤子线、启明星、黄昏星等 K 线形态。配合成交量确认，5m 周期高频交易，每日几十次信号。',
    tags: ['短线', 'K线形态', '高频'],
    params: { timeframe: '5m', stoploss: '0.6%' },
    perf: '待测试',
    risk: '高',
  },
  {
    name: 'VegasStrategy',
    title: '维加斯通道短线',
    description: 'EMA144 定方向 + EMA12/24 隧道回踩。只在主流方向做顺势单，回踩隧道不破时 MACD 金叉/死叉确认入场，5m 周期交易。',
    tags: ['短线', '维加斯', '趋势'],
    params: { timeframe: '5m', ema: '12/24/72/144' },
    perf: '待测试',
    risk: '中高',
  },
  {
    name: 'MacdDivergenceStrategy',
    title: 'MACD 背离超短线',
    description: '检测 MACD 顶/底背离：价格创新低但 MACD 抬高 = 底背离做多；价格创新高但 MACD 降低 = 顶背离做空。1m 周期超高频。',
    tags: ['超短线', 'MACD', '背离', '高频'],
    params: { timeframe: '1m', stoploss: '0.4%' },
    perf: '待测试',
    risk: '高',
  },
  {
    name: 'TimeStrategy',
    title: '交易时段策略',
    description: '只在亚盘/伦敦盘/美盘开盘时段交易，利用开盘流动性爆发。非交易时段不交易，降低无效震荡损耗。5m 周期。',
    tags: ['短线', '时段', '开盘'],
    params: { timeframe: '5m', sessions: 'Asia/London/US' },
    perf: '待测试',
    risk: '中',
  },
  {
    name: 'ChanTheoryStrategy',
    title: '缠论三买/三卖 🏆',
    description: '缠论第三类买卖点。96根K线中枢+MACD过滤。回测:15m 41%胜率 +14.9%收益 夏普1.29。推荐5x杠杆+20%仓位。',
    tags: ['短线', '缠论', '推荐', '中枢'],
    params: { timeframe: '15m', leverage: '5x' },
    perf: '+14.91%',
    risk: '中高',
  },
  // ── 专业短线策略 ──
  {
    name: 'VwapReversionStrategy',
    title: 'VWAP 均值回归',
    description: '机构级策略。价格偏离 VWAP 超 0.15% + RSI 超买/卖时入场，回归 VWAP 出场。做市商常用，胜率 55-65%。5m 周期。',
    tags: ['短线', 'VWAP', '均值回归', '机构'],
    params: { timeframe: '5m', deviation: '0.15%' },
    perf: '待测试',
    risk: '中',
  },
  {
    name: 'MultiTFMomentumStrategy',
    title: '多周期动量',
    description: '1h 定方向(大趋势) → 5m 找入场点(回踩/反弹)。只顺势交易，不做回调。专业交易员核心方法，盈亏比 1.5:1+。',
    tags: ['短线', '动量', '多周期', '趋势'],
    params: { timeframe: '5m', tfs: '1h+5m' },
    perf: '待测试',
    risk: '中低',
  },
  {
    name: 'VolatilityBreakoutStrategy',
    title: '波动率突破',
    description: 'Bollinger Bands 缩口到极致后放量突破入场。抓趋势启动点，盈亏比高(2:1+)。适合 BTC 这种有爆发力的品种。',
    tags: ['短线', '突破', '波动率', '动量'],
    params: { timeframe: '5m', bb_period: 20 },
    perf: '待测试',
    risk: '中高',
  },
  {
    name: 'ZScoreReversionStrategy',
    title: 'Z-Score 均值回归 ⭐',
    description: '统计学派策略。计算价格偏离均值的标准分数(Z>2.5)，严重偏离后回归概率>95%。5m周期，2x杠杆+做市费率可实现正期望。回测: 51%胜率 夏普0.33',
    tags: ['短线', '均值回归', '统计', '推荐'],
    params: { timeframe: '5m', leverage: '2x', fee: '0.02%' },
    perf: '+0.05%',
    risk: '低',
  },
  {
    name: 'ZScorePro',
    title: 'Z-Score PRO ⭐🏆',
    description: '高产版！Z-Score均值回归+10x杠杆+0.02%做市费率。回测:+27% 胜率52% 夏普4.0。⚠️ 必须设:杠杆10x、费率0.02%、本金30-50%/笔。默认参数会亏！',
    tags: ['短线', '高产', '推荐', '10x'],
    params: { timeframe: '5m', leverage: '10x', fee: '0.02%' },
    perf: '+26.88%',
    risk: '高',
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
        {filtered.map(s => (
          <div key={s.name} className="border rounded-lg p-4 hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between mb-2">
              <div>
                <h3 className="font-semibold text-sm">{s.title}</h3>
                <code className="text-xs text-gray-400">{s.name}.py</code>
              </div>
              <button
                className="text-xs bg-blue-50 text-blue-600 px-2 py-1 rounded hover:bg-blue-100"
                onClick={() => onSelect(s.name)}
              >使用此策略</button>
            </div>
            <p className="text-xs text-gray-600 mb-3 leading-relaxed">{s.description}</p>
            <div className="flex flex-wrap gap-1 mb-2">
              {s.tags.map(t => (
                <span key={t} className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">{t}</span>
              ))}
            </div>
            <div className="flex gap-3 text-xs text-gray-400 border-t pt-2">
              <span>收益: {s.perf}</span>
              <span>风险: {s.risk}</span>
              <span>粒度: {s.params.timeframe || '1h'}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
