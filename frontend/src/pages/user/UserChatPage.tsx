/** 用户端在线咨询页（12 §3）：会话列表 + 对话流 + SSE 流式 + 实时事件同步。 */

import { PlusOutlined } from '@ant-design/icons';
import { Alert, Button, Empty, Input, Spin, Typography } from 'antd';
import dayjs from 'dayjs';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import ChatConversation from '../../components/chat/ChatConversation';
import type { DisplayMessage } from '../../components/chat/types';
import {
  getUserSession,
  listUserSessions,
  markUserSessionRead,
  userChatStream,
  type UserSessionItem,
} from '../../api/user';
import { getUserAccessToken } from '../../api/token';
import { connectEventStream } from '../../utils/eventStream';

const QUICK_QUESTIONS = ['商品签收后几天可以退货？', '退款多久到账？', '查询我的订单'];
let tempSeq = 0;

function nextTempId(prefix: string): string {
  tempSeq += 1;
  return `${prefix}-${Date.now()}-${tempSeq}`;
}

export default function UserChatPage() {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [sessionStatus, setSessionStatus] = useState<string>('active');
  const [streaming, setStreaming] = useState(false);
  const [connState, setConnState] = useState<'connected' | 'reconnecting'>('connected');
  const [input, setInput] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  const streamIdRef = useRef<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  const setActiveSession = useCallback((id: string | null) => {
    sessionIdRef.current = id;
    setSessionId(id);
  }, []);

  const { data: sessions, isLoading } = useQuery({
    queryKey: ['user-sessions'],
    queryFn: () => listUserSessions({ page: 1, page_size: 20 }),
  });

  const loadSession = useCallback(async (id: string) => {
    abortRef.current?.abort();
    setActiveSession(id);
    const detail = await getUserSession(id);
    setSessionStatus(detail.session.status);
    setMessages(
      detail.messages.map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        created_at: m.created_at,
      })),
    );
    void markUserSessionRead(id);
    void queryClient.invalidateQueries({ queryKey: ['user-sessions'] });
  }, [queryClient, setActiveSession]);

  // 进入页面自动恢复最近 active 会话（12 §3.2）
  useEffect(() => {
    if (sessions && sessions.items.length > 0 && !sessionId) {
      const active = sessions.items.find((s) => s.status === 'active') ?? sessions.items[0];
      void loadSession(active.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessions]);

  const refetchCurrent = useCallback(async () => {
    if (sessionId) {
      const detail = await getUserSession(sessionId);
      setSessionStatus(detail.session.status);
      setMessages(
        detail.messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          created_at: m.created_at,
        })),
      );
    }
  }, [sessionId]);

  // 实时事件（scope=user）：人工回复 / 工单状态变化（11 §9）
  useEffect(() => {
    const off = connectEventStream(
      '/api/stream/events?scope=user',
      {
        'message.new': () => {
          void refetchCurrent();
          void queryClient.invalidateQueries({ queryKey: ['user-sessions'] });
        },
        'ticket.claimed': () => {
          void refetchCurrent();
          void queryClient.invalidateQueries({ queryKey: ['user-tickets'] });
        },
        'ticket.closed': () => {
          void refetchCurrent();
          void queryClient.invalidateQueries({ queryKey: ['user-tickets'] });
        },
        'ticket.updated': () => void queryClient.invalidateQueries({ queryKey: ['user-tickets'] }),
      },
      {
        token: getUserAccessToken(),
        onOpen: () => setConnState('connected'),
        onError: () => setConnState('reconnecting'),
        onReconnect: () => {
          setConnState('connected');
          void refetchCurrent();
          void queryClient.invalidateQueries({ queryKey: ['user-sessions'] });
        },
      },
    );
    return off;
  }, [refetchCurrent, queryClient]);

  const appendStreaming = (content: string) => {
    const id = streamIdRef.current;
    if (!id) return;
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, content: m.content + content } : m)),
    );
  };

  const sendMessage = async (text: string) => {
    const content = text.trim();
    if (!content || streaming) return;
    // 【修复 M8】临时 id 生成移到模块级，规避 react-hooks/purity 误报
    const tempUser = nextTempId('tmp-u');
    const tempAi = nextTempId('tmp-a');
    streamIdRef.current = tempAi;
    setMessages((prev) => [
      ...prev,
      { id: tempUser, role: 'user', content, created_at: new Date().toISOString() },
      { id: tempAi, role: 'assistant', content: '', created_at: new Date().toISOString() },
    ]);
    setStreaming(true);
    const abort = new AbortController();
    abortRef.current = abort;
    try {
      await userChatStream(
        { session_id: sessionId, message: content },
        (ev) => {
          if (ev.event === 'message_start') {
            setActiveSession(ev.data.session_id);
          } else if (ev.event === 'token') {
            appendStreaming(ev.data.content);
          } else if (ev.event === 'citations') {
            const id = streamIdRef.current;
            if (id) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === id
                    ? {
                        ...m,
                        citations: ev.data.citations.map((c) => ({
                          document_name: c.document_name,
                          question: c.question,
                        })),
                      }
                    : m,
                ),
              );
            }
          } else if (ev.event === 'error') {
            appendStreaming(`\n（${ev.data.message}）`);
          }
        },
        abort.signal,
      );
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        appendStreaming('\n（连接失败，请重试）');
      }
    } finally {
      setStreaming(false);
      streamIdRef.current = null;
      // 以服务端为准同步消息（含系统消息/转人工状态）
      const sid = sessionId;
      if (sid) {
        void getUserSession(sid)
          .then((detail) => {
            // 【修复 M2】流式期间切换会话：仅当当前会话未变时应用结果，避免串台
            if (sid !== sessionIdRef.current) return;
            setSessionStatus(detail.session.status);
            setMessages(
              detail.messages.map((m) => ({
                id: m.id,
                role: m.role,
                content: m.content,
                created_at: m.created_at,
              })),
            );
          })
          .catch(() => undefined);
      }
      void queryClient.invalidateQueries({ queryKey: ['user-sessions'] });
      void queryClient.invalidateQueries({ queryKey: ['user-tickets'] });
    }
  };

  const stopStreaming = () => {
    abortRef.current?.abort();
  };

  const newSession = () => {
    if (streaming) return;
    abortRef.current?.abort();
    setActiveSession(null);
    setMessages([]);
    setSessionStatus('active');
  };

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 64px)', background: '#fff' }}>
      {/* 左栏：最近会话 */}
      <div style={{ width: 280, borderRight: '1px solid #E5E7EB', padding: 16, overflow: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
          <Typography.Text strong>最近会话</Typography.Text>
          <Button size="small" icon={<PlusOutlined />} onClick={newSession}>
            新会话
          </Button>
        </div>
        {isLoading ? (
          <Spin />
        ) : (
          (sessions?.items ?? []).map((s: UserSessionItem) => (
            <div
              key={s.id}
              onClick={() => void loadSession(s.id)}
              style={{
                padding: '10px 12px',
                borderRadius: 8,
                cursor: 'pointer',
                marginBottom: 6,
                background: s.id === sessionId ? '#EFF6FF' : '#F9FAFB',
                border: s.id === sessionId ? '1px solid #BFDBFE' : '1px solid transparent',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                <Typography.Text style={{ color: s.status === 'active' ? '#3B82F6' : '#6B7280' }}>
                  {s.status === 'active' ? '进行中' : s.status === 'transferred' ? '已转人工' : '已结束'}
                </Typography.Text>
                <Typography.Text type="secondary">{dayjs(s.updated_at).format('MM-DD HH:mm')}</Typography.Text>
              </div>
              <div style={{ fontSize: 13, color: '#374151', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {s.last_message || '（空会话）'}
              </div>
            </div>
          ))
        )}
        {(sessions?.items ?? []).length === 0 && !isLoading && <Empty description="暂无会话" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
      </div>

      {/* 右栏：对话区 */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {connState === 'reconnecting' && (
          <Alert type="warning" showIcon banner message="连接已断开，正在重连…" />
        )}
        {sessionStatus === 'transferred' && (
          <Alert
            type="info"
            showIcon
            banner
            message="已转人工客服，您仍可继续留言，消息将保存供人工客服查看"
          />
        )}
        <div style={{ flex: 1, overflow: 'auto', background: '#F9FAFB' }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', padding: 60 }}>
              <Typography.Title level={4}>您好，我是 AI 智能客服</Typography.Title>
              <Typography.Paragraph type="secondary">我可以回答售后政策问题，也可以帮您查询订单</Typography.Paragraph>
              <div>
                {QUICK_QUESTIONS.map((q) => (
                  <Button key={q} style={{ margin: 6 }} onClick={() => void sendMessage(q)}>
                    {q}
                  </Button>
                ))}
              </div>
            </div>
          )}
          <ChatConversation messages={messages} />
        </div>
        <div style={{ padding: 16, borderTop: '1px solid #E5E7EB' }}>
          <Input.TextArea
            value={input}
            onChange={(e) => setInput(e.target.value.slice(0, 500))}
            placeholder="输入您的问题（Enter 发送，Shift+Enter 换行）"
            autoSize={{ minRows: 2, maxRows: 5 }}
            disabled={streaming}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void sendMessage(input);
                setInput('');
              }
            }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
            <Typography.Text type="secondary" style={{ fontSize: 12, marginRight: 'auto' }}>
              {input.length}/500
            </Typography.Text>
            {streaming ? (
              <Button danger onClick={stopStreaming}>
                停止
              </Button>
            ) : (
              <Button type="primary" disabled={!input.trim()} onClick={() => { void sendMessage(input); setInput(''); }}>
                发送
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
