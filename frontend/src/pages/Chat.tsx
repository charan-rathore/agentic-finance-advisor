import { useState, useRef, useEffect } from 'react'
import {
  Send, Bot, User, Loader2, Languages, ChevronRight,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { api } from '../lib/api'
import { cn, confidenceLabel } from '../lib/utils'
import type { Profile } from '../lib/api'

interface Props {
  profile: Profile
}

interface Message {
  role: 'user' | 'bot'
  content: string
  sources?: string[]
  confidence?: number
  fast_path?: string | null
}

const SUGGESTED = [
  'How much should I invest in SIP?',
  'What is ELSS and should I invest in it?',
  'Explain Nifty 50 in simple terms',
  'How to build an emergency fund?',
  'Is now a good time to start SIP?',
  'What is the difference between LTCG and STCG?',
]

export default function Chat({ profile }: Props) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'bot',
      content: `Hello ${profile.name.split(' ')[0]}! 👋 I'm your personal AI investment advisor. Ask me anything about investing, mutual funds, tax saving, or market trends — in plain English or हिंदी.`,
      confidence: 1,
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [hindi, setHindi] = useState(false)
  const [market, setMarket] = useState<'india' | 'global'>('india')
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async (text: string) => {
    if (!text.trim() || loading) return
    const q = text.trim()
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: q }])
    setLoading(true)

    try {
      const res = await api.chat(q, hindi, market)
      setMessages((prev) => [
        ...prev,
        {
          role: 'bot',
          content: res.answer,
          sources: res.sources,
          confidence: res.confidence,
          fast_path: res.fast_path,
        },
      ])
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'bot', content: 'Sorry, I encountered an error. Please try again.', confidence: 0 },
      ])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send(input)
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-0px)] lg:h-screen max-h-screen">
      {/* Header */}
      <div className="border-b border-surface-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 lg:px-6 py-3 flex-shrink-0">
        <div className="flex items-center justify-between gap-3 max-w-3xl mx-auto">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-brand-600 rounded-full flex items-center justify-center">
              <Bot size={16} className="text-white" />
            </div>
            <div>
              <div className="font-semibold text-sm text-gray-900 dark:text-white">AI Advisor</div>
              <div className="text-xs text-gray-400 dark:text-gray-500">Powered by Gemini · Grounded in live data</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Market toggle */}
            <div className="flex rounded-lg border border-surface-200 dark:border-gray-600 overflow-hidden text-xs">
              <button
                onClick={() => setMarket('india')}
                className={cn(
                  'px-2.5 py-1.5 font-medium transition-colors',
                  market === 'india'
                    ? 'bg-brand-600 text-white'
                    : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-surface-50 dark:hover:bg-gray-700'
                )}
              >
                🇮🇳 India
              </button>
              <button
                onClick={() => setMarket('global')}
                className={cn(
                  'px-2.5 py-1.5 font-medium transition-colors',
                  market === 'global'
                    ? 'bg-brand-600 text-white'
                    : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-surface-50 dark:hover:bg-gray-700'
                )}
              >
                🌐 Global
              </button>
            </div>
            {/* Hindi toggle */}
            <button
              onClick={() => setHindi(!hindi)}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-colors',
                hindi
                  ? 'bg-violet-600 border-violet-600 text-white'
                  : 'border-surface-200 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-surface-50 dark:hover:bg-gray-700'
              )}
            >
              <Languages size={13} />
              हिंदी
            </button>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto bg-surface-50 dark:bg-gray-950">
        <div className="max-w-3xl mx-auto px-4 py-4 space-y-4">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={cn('flex gap-3', msg.role === 'user' ? 'justify-end' : 'justify-start')}
            >
              {msg.role === 'bot' && (
                <div className="w-7 h-7 bg-brand-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Bot size={13} className="text-white" />
                </div>
              )}
              <div className={cn('max-w-[85%] space-y-1.5', msg.role === 'user' ? 'items-end' : 'items-start')}>
                <div
                  className={cn(
                    'rounded-2xl px-4 py-3 text-sm',
                    msg.role === 'user'
                      ? 'bg-brand-600 text-white rounded-tr-sm'
                      : 'bg-white dark:bg-gray-800 border border-surface-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 rounded-tl-sm'
                  )}
                >
                  {msg.role === 'bot' ? (
                    <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  ) : (
                    msg.content
                  )}
                </div>
                {msg.role === 'bot' && msg.confidence != null && msg.confidence < 1 && (
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={cn(
                      'badge border text-xs',
                      confidenceLabel(msg.confidence).color
                    )}>
                      Confidence: {(msg.confidence * 100).toFixed(0)}% · {confidenceLabel(msg.confidence).label}
                    </span>
                    {msg.fast_path && (
                      <span className="badge bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800 text-xs">
                        Fast answer
                      </span>
                    )}
                  </div>
                )}
                {msg.role === 'bot' && msg.sources && msg.sources.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {msg.sources.slice(0, 4).map((src, j) => (
                      <span
                        key={j}
                        className="text-xs px-2 py-0.5 rounded-full bg-surface-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 border border-surface-200 dark:border-gray-600"
                      >
                        {src.split('/').pop()?.replace('.md', '') || src}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              {msg.role === 'user' && (
                <div className="w-7 h-7 bg-surface-200 dark:bg-gray-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                  <User size={13} className="text-gray-600 dark:text-gray-300" />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex gap-3">
              <div className="w-7 h-7 bg-brand-600 rounded-full flex items-center justify-center flex-shrink-0">
                <Bot size={13} className="text-white" />
              </div>
              <div className="bg-white dark:bg-gray-800 border border-surface-200 dark:border-gray-700 rounded-2xl rounded-tl-sm px-4 py-3">
                <Loader2 size={16} className="animate-spin text-brand-500" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Suggested questions (only at start) */}
      {messages.length === 1 && (
        <div className="border-t border-surface-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3 flex-shrink-0">
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-2 max-w-3xl mx-auto">Suggested questions</p>
          <div className="flex gap-2 overflow-x-auto pb-1 max-w-3xl mx-auto scrollbar-hide">
            {SUGGESTED.map((q, i) => (
              <button
                key={i}
                onClick={() => send(q)}
                className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-surface-200 dark:border-gray-600 bg-surface-50 dark:bg-gray-800 text-xs text-gray-600 dark:text-gray-300 hover:border-brand-300 dark:hover:border-brand-700 hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
              >
                {q}
                <ChevronRight size={11} />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-surface-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3 flex-shrink-0">
        <div className="max-w-3xl mx-auto flex items-end gap-2">
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={hindi ? 'अपना सवाल पूछें...' : 'Ask anything about investing...'}
            className="flex-1 input-field resize-none min-h-[42px] max-h-32 py-2.5 overflow-y-auto"
            style={{ lineHeight: '1.4' }}
          />
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || loading}
            className="btn-primary p-2.5 flex-shrink-0"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}
