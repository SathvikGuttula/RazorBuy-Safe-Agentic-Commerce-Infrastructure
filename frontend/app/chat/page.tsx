"use client";

import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { openRazorpayCheckout } from "@/lib/razorpay";
import {
  Send, Bot, User, Loader2, Shield, CheckCircle2,
  XCircle, AlertTriangle, Sparkles, CreditCard, PlusCircle
} from "lucide-react";

interface Step {
  step: number;
  type: string;
  tool?: string;
  arguments?: any;
  result_summary?: string;
  status?: string;
  latency_ms?: number;
}

interface ChatMessage {
  role: "user" | "agent";
  content: string;
  steps?: Step[];
  warnings?: string[];
  total_steps?: number;
  orderCreated?: {
    order_id: string;
    total: number;
    status: string;
  };
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [payingOrderId, setPayingOrderId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load chat history from localStorage on mount
  useEffect(() => {
    const savedSession = localStorage.getItem("razorbuy_session_id");
    const savedMessages = localStorage.getItem("razorbuy_chat_messages");
    if (savedSession) setSessionId(savedSession);
    if (savedMessages) {
      try {
        setMessages(JSON.parse(savedMessages));
      } catch (e) {}
    }
  }, []);

  // Save chat history to localStorage on change
  useEffect(() => {
    if (sessionId) localStorage.setItem("razorbuy_session_id", sessionId);
    if (messages.length > 0) {
      localStorage.setItem("razorbuy_chat_messages", JSON.stringify(messages));
    }
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, sessionId]);

  const handleNewChat = async () => {
    try {
      await fetch("/api/admin/reset", { method: "POST" });
    } catch (e) {
      // Silently continue if reset fails
    }
    setSessionId(undefined);
    setMessages([]);
    localStorage.removeItem("razorbuy_session_id");
    localStorage.removeItem("razorbuy_chat_messages");
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);

    try {
      const res = await api.chat(userMsg, sessionId);
      setSessionId(res.session_id);

      // Extract created order details if any tool call created one
      let orderCreated = undefined;
      for (const step of res.steps || []) {
        if (step.tool === "create_order" && step.status === "SUCCESS") {
          orderCreated = {
            order_id: "order_created",
            total: 0,
            status: "APPROVED",
          };
        }
      }

      setMessages((prev) => [
        ...prev,
        {
          role: "agent",
          content: res.response,
          steps: res.steps,
          warnings: res.warnings,
          total_steps: res.total_steps,
          orderCreated,
        },
      ]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        { role: "agent", content: `Error: ${err.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] max-w-5xl mx-auto">
      <div className="flex items-center justify-between pb-4 border-b border-[#2e3345] mb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">AI Commerce Agent</h1>
          <p className="text-xs text-gray-400 mt-0.5">
            Discover products, negotiate offers, and transact under policy control
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleNewChat}
            className="flex items-center gap-1.5 bg-[#242836] hover:bg-[#2e3345] border border-[#2e3345] text-gray-300 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
          >
            <PlusCircle className="w-3.5 h-3.5 text-indigo-400" />
            New Chat
          </button>
          <div className="flex items-center gap-2 bg-[#1a1d27] border border-[#2e3345] px-3 py-1.5 rounded-lg text-xs text-indigo-400 font-medium">
            <Shield className="w-3.5 h-3.5" />
            <span>Policy Engine Active</span>
          </div>
        </div>
      </div>

      {/* Chat History */}
      <div className="flex-1 overflow-y-auto space-y-6 pr-2">
        {messages.length === 0 && (
          <div className="text-center py-20 text-gray-500">
            <div className="w-16 h-16 rounded-2xl bg-indigo-600/10 border border-indigo-500/20 flex items-center justify-center mx-auto mb-4 text-indigo-400">
              <Bot className="w-8 h-8" />
            </div>
            <h2 className="text-lg font-semibold text-gray-300">Welcome to RazorBuy</h2>
            <p className="text-sm max-w-md mx-auto mt-1 text-gray-500">
              Ask me to search products, negotiate discounts, or buy items within policy limits.
            </p>
            <div className="flex flex-wrap justify-center gap-2 mt-6">
              {[
                "Find wireless earbuds under ₹3,000 with ANC",
                "Can you give me 10% discount on P101 and buy it?",
                "Buy StudioMax Pro headphones",
              ].map((suggestion, idx) => (
                <button
                  key={idx}
                  onClick={() => setInput(suggestion)}
                  className="text-xs bg-[#1a1d27] hover:bg-[#242836] border border-[#2e3345] text-gray-300 px-3 py-2 rounded-xl transition-all"
                >
                  &quot;{suggestion}&quot;
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex gap-4 ${msg.role === "user" ? "justify-end" : ""}`}
          >
            {msg.role === "agent" && (
              <div className="w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center flex-shrink-0 text-white shadow-md shadow-indigo-600/20">
                <Bot className="w-5 h-5" />
              </div>
            )}

            <div
              className={`max-w-2xl rounded-2xl p-5 ${
                msg.role === "user"
                  ? "bg-indigo-600 text-white shadow-lg shadow-indigo-600/20"
                  : "bg-[#1a1d27] border border-[#2e3345] text-gray-200"
              }`}
            >
              <p className="whitespace-pre-wrap leading-relaxed text-sm">{msg.content}</p>

              {/* Injection Warnings */}
              {msg.warnings && msg.warnings.length > 0 && (
                <div className="mt-3 p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-amber-300 text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0 text-amber-400" />
                  <span>{msg.warnings[0]}</span>
                </div>
              )}

              {/* Steps Trace */}
              {msg.steps && msg.steps.length > 0 && (
                <div className="mt-4 pt-3 border-t border-[#2e3345]">
                  <div className="flex items-center justify-between text-[11px] text-gray-400 mb-2">
                    <span className="font-semibold uppercase tracking-wider text-gray-500">
                      Reasoning & Tool Execution Trace
                    </span>
                    <span>{msg.total_steps} steps</span>
                  </div>
                  <div className="space-y-1.5">
                    {msg.steps.map((step, j) => (
                      <div
                        key={j}
                        className="flex items-center gap-2 text-xs bg-[#242836]/60 p-2.5 rounded-lg border border-[#2e3345]/50"
                      >
                        {step.type === "tool_call" ? (
                          <>
                            {step.status === "SUCCESS" ? (
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                            ) : step.status === "BLOCKED" ? (
                              <XCircle className="w-3.5 h-3.5 text-rose-400 flex-shrink-0" />
                            ) : (
                              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
                            )}
                            <span className="font-mono text-indigo-400 font-medium">
                              {step.tool}
                            </span>
                            <span className="text-gray-400 truncate">
                              {step.result_summary}
                            </span>
                          </>
                        ) : (
                          <>
                            <Sparkles className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0" />
                            <span className="text-gray-400 italic">
                              Synthesizing response & verifying output...
                            </span>
                          </>
                        )}
                        <span className="text-[10px] text-gray-500 ml-auto font-mono">
                          {step.latency_ms}ms
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {msg.role === "user" && (
              <div className="w-9 h-9 rounded-xl bg-[#242836] border border-[#2e3345] flex items-center justify-center flex-shrink-0 text-gray-300">
                <User className="w-5 h-5" />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex gap-4">
            <div className="w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center flex-shrink-0 text-white">
              <Bot className="w-5 h-5" />
            </div>
            <div className="bg-[#1a1d27] border border-[#2e3345] rounded-2xl p-4 flex items-center gap-3">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
              <span className="text-xs text-gray-400 font-medium">
                Reasoning & evaluating policy boundaries...
              </span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input Box */}
      <div className="mt-4 flex gap-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          placeholder="Ask RazorBuy to find, negotiate, or order products..."
          className="flex-1 bg-[#1a1d27] border border-[#2e3345] rounded-xl px-4 py-3.5 text-sm text-gray-200 outline-none focus:border-indigo-500 transition-all placeholder:text-gray-500"
          disabled={loading}
        />
        <button
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white px-5 py-3.5 rounded-xl font-medium transition-all shadow-lg shadow-indigo-600/30 flex items-center justify-center"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}