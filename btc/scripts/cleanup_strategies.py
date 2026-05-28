#!/usr/bin/env python3
"""Replace the STRATEGIES array with cleaned up version"""
import re
from pathlib import Path

filepath = Path('btc/frontend/src/app/page.tsx')
content = filepath.read_text()

# Find the STRATEGIES array boundaries
start = content.find("const STRATEGIES = [")
end = content.find("\n]", start) + 2  # include the ]; 

new_strategies = '''const STRATEGIES = [
  {
    name: 'RealChanTheory',
    title: '🏆 真正缠论',
    description: '完整缠论(分型→笔→中枢→买卖点)+MACD背驰。1h 68笔 +16.16% 胜率41% 夏普3.64 回撤3.7%。只做1买1卖2卖高胜率信号。每笔标注详细原因。',
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
]'''

content = content[:start] + new_strategies + content[end:]
filepath.write_text(content)
print(f"Done! Replaced strategies (line {start})")
