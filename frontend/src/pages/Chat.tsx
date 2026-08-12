/** 智能客服对话页（03 §3–7 / 01 组件规范）。 */

import {
  CheckCircleOutlined,
  DeleteOutlined,
  PlusOutlined,
  RobotOutlined,
  SendOutlined,
  StopOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Avatar,
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Popover,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ApiError } from '../api/client';
import {
  chatStream,
  createFeedback,
  getSession,
  listModelProfiles,
  listSessions,
  type ChatEvent,
  type ChatForm,
  type ChatFormField,
  type ChatSession,
  type Citation,
  type ModelProfile,
} from '../api/chat';
import { listKnowledgeBases } from '../api/knowledge';
import { useAuthStore } from '../stores/auth';

const QUICK_QUESTIONS = [
  '查询订单',
  '退款政策',
  '商品签收几天可以退货',
  '我要投诉转人工',
];

interface UiMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  intent?: string | null;
  form?: ChatForm | null;
  formSubmitted?: boolean;
  stopped?: boolean;
  error?: string;
}

function scoreColor(score: number): string {
  if (score >= 70) return 'green';
  if (score >= 40) return 'orange';
  return 'red';
}

/** 渲染消息内容，[n] 转为可点击引用编号 */
function renderWithRefs(content: string, onRef: (index: number) => void) {
  const parts = content.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (m) {
      const idx = Number(m[1]);
      return (
        <a
          key={i}
          style={{ color: '#2563EB', fontWeight: 600, margin: '0 1px' }}
          onClick={(e) => {
            e.preventDefault();
            onRef(idx);
          }}
        >
          [{idx}]
        </a>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

/** 对话内表单卡片（03 §4.5） */
function FormCard({
  form,
  submitted,
  onSubmit,
}: {
  form: ChatForm;
  submitted: boolean;
  onSubmit: (values: Record<string, string>) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const validate = (field: ChatFormField, value: string): string => {
    if (field.required && !value) return field.message || '该项必填';
    if (value && field.pattern) {
      try {
        if (!new RegExp(field.pattern).test(value)) return field.message || '格式不正确';
      } catch {
        // 忽略非法正则
      }
    }
    return '';
  };

  const handleSubmit = () => {
    const nextErrors: Record<string, string> = {};
    for (const field of form.fields) {
      const err = validate(field, values[field.name] ?? '');
      if (err) nextErrors[field.name] = err;
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    setSubmitting(true);
    onSubmit(values);
  };

  if (submitted) {
    return (
      <div style={{ marginTop: 8, color: '#16A34A', fontSize: 13 }}>
        <CheckCircleOutlined /> 表单已提交，订单号/联系方式已作为上下文继续对话
      </div>
    );
  }

  return (
    <div
      style={{
        marginTop: 8,
        border: '1px solid #E5E7EB',
        borderRadius: 10,
        padding: 12,
        background: '#FFFFFF',
        maxWidth: 320,
      }}
    >
      {form.fields.map((field) => (
        <div key={field.name} style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 13, color: '#6B7280', marginBottom: 4 }}>
            {field.label}
            {field.required && <span style={{ color: '#EF4444' }}> *</span>}
          </div>
          <Input
            value={values[field.name] ?? ''}
            status={errors[field.name] ? 'error' : undefined}
            placeholder={field.message}
            onChange={(e) => {
              setValues((v) => ({ ...v, [field.name]: e.target.value }));
              setErrors((er) => ({ ...er, [field.name]: '' }));
            }}
          />
          {errors[field.name] && (
            <div style={{ color: '#EF4444', fontSize: 12, marginTop: 2 }}>
              {errors[field.name]}
            </div>
          )}
        </div>
      ))}
      <Button type="primary" size="small" loading={submitting} onClick={handleSubmit}>
        提交
      </Button>
    </div>
  );
}

export default function ChatPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [kbIds, setKbIds] = useState<string[]>([]);
  const [modelProfiles, setModelProfiles] = useState<ModelProfile[]>([]);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [addCitationOpen, setAddCitationOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const nearBottomRef = useRef(true);
  const messageIdRef = useRef<string | null>(null);

  const { data: knowledgeBases = [] } = useQuery({
    queryKey: ['knowledge-bases'],
    queryFn: listKnowledgeBases,
  });
  const kbNameMap = useMemo(
    () => Object.fromEntries(knowledgeBases.map((kb) => [kb.id, kb.name])),
    [knowledgeBases],
  );

  // 初始化：会话列表 + 知识库默认 + 模型配置（admin）
  useEffect(() => {
    (async () => {
      try {
        const [sessionPage, profiles] = await Promise.all([
          listSessions({ page: 1, page_size: 20 }),
          isAdmin ? listModelProfiles().catch(() => []) : Promise.resolve([]),
        ]);
        setSessions(sessionPage.items);
        setModelProfiles(profiles);
        const def = profiles.find((p) => p.is_default) ?? profiles[0];
        if (def) setSelectedModel(def.id);
        if (sessionPage.items.length > 0) {
          await loadSession(sessionPage.items[0].id);
        }
      } catch (err) {
        message.error(err instanceof ApiError ? err.message : '初始化失败');
      } finally {
        setInitializing(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshSessions = useCallback(async () => {
    try {
      const page = await listSessions({ page: 1, page_size: 20 });
      setSessions(page.items);
    } catch {
      // 会话列表刷新失败不阻塞对话
    }
  }, []);

  const loadSession = useCallback(async (id: string) => {
    try {
      const detail = await getSession(id);
      setSessionId(detail.session.id);
      setKbIds(detail.session.kb_ids ?? []);
      setMessages(detail.messages);
      setCitations([]);
      setStreaming(false);
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '会话加载失败');
    }
  }, []);

  const startNewSession = () => {
    abortRef.current?.abort();
    setSessionId(null);
    setMessages([]);
    setCitations([]);
    setStreaming(false);
  };

  // 自动滚动：仅当用户停留在底部时跟随
  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };
  useEffect(() => {
    const el = scrollRef.current;
    if (el && nearBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, streaming]);

  const stopGenerating = () => {
    abortRef.current?.abort();
    setStreaming(false);
    setMessages((msgs) =>
      msgs.map((m, i) => (i === msgs.length - 1 && m.role === 'assistant' ? { ...m, stopped: true } : m)),
    );
  };

  const sendMessage = async (text: string, formData?: Record<string, string>) => {
    const content = text.trim();
    if (!content || streaming) return;
    if (kbIds.length === 0) {
      message.warning('请先选择至少一个知识库');
      return;
    }

    setMessages((msgs) => [
      ...msgs,
      { id: `local-${Date.now()}`, role: 'user', content },
      { id: 'streaming', role: 'assistant', content: '', form: null },
    ]);
    setStreaming(true);
    setCitations([]);
    setInput('');

    const controller = new AbortController();
    abortRef.current = controller;
    let fullText = '';

    const handleEvent = (ev: ChatEvent) => {
      if (ev.event === 'message_start') {
        setSessionId(ev.data.session_id);
        messageIdRef.current = null;
      } else if (ev.event === 'token') {
        fullText += ev.data.content;
        setMessages((msgs) =>
          msgs.map((m) =>
            m.id === 'streaming' ? { ...m, content: fullText } : m,
          ),
        );
      } else if (ev.event === 'form') {
        setMessages((msgs) =>
          msgs.map((m) => (m.id === 'streaming' ? { ...m, form: ev.data } : m)),
        );
      } else if (ev.event === 'citations') {
        setCitations(ev.data.citations);
      } else if (ev.event === 'done') {
        messageIdRef.current = ev.data.message_id;
        setMessages((msgs) =>
          msgs.map((m) =>
            m.id === 'streaming'
              ? {
                  ...m,
                  id: ev.data.message_id,
                  intent: ev.data.intent,
                  formSubmitted: false,
                }
              : m,
          ),
        );
        if (ev.data.ticket_no) {
          setMessages((msgs) => [
            ...msgs.map((m) => (m.id === 'streaming' ? { ...m, id: ev.data.message_id } : m)),
            {
              id: `sys-${Date.now()}`,
              role: 'system',
              content: `已为您转接人工客服，工单号 ${ev.data.ticket_no}，请稍候`,
              intent: 'transfer',
            },
          ]);
        }
        setStreaming(false);
        void refreshSessions();
      } else if (ev.event === 'error') {
        setMessages((msgs) =>
          msgs.map((m) =>
            m.id === 'streaming'
              ? { ...m, content: `（错误：${ev.data.message}）`, error: ev.data.message }
              : m,
          ),
        );
        setStreaming(false);
      }
    };

    try {
      await chatStream(
        {
          session_id: sessionId,
          kb_ids: kbIds,
          message: content,
          model_profile_id: selectedModel,
          form_data: formData ?? null,
        },
        handleEvent,
        controller.signal,
      );
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setMessages((msgs) =>
          msgs.map((m) =>
            m.id === 'streaming' ? { ...m, content: `（错误：${(err as Error).message}）` } : m,
          ),
        );
        setStreaming(false);
      }
    }
    // 表单卡片标记已提交（提交后收起）
    if (formData) {
      setMessages((msgs) =>
        msgs.map((m) => (m.form ? { ...m, formSubmitted: true } : m)),
      );
    }
  };

  const scrollToCitation = (index: number) => {
    document.getElementById(`citation-${index}`)?.scrollIntoView({
      behavior: 'smooth',
      block: 'center',
    });
  };

  const sendFeedback = async (
    action: 'delete' | 'invalid' | 'add',
    citation: Citation,
    reason?: string,
  ) => {
    if (!messageIdRef.current || !sessionId) {
      message.warning('当前回答尚未完成，请稍后操作');
      return;
    }
    try {
      await createFeedback({
        session_id: sessionId,
        message_id: messageIdRef.current,
        chunk_id: citation.chunk_id,
        action,
        reason,
      });
      message.success('反馈已记录');
      if (action === 'delete') {
        setCitations((list) => list.filter((c) => c.chunk_id !== citation.chunk_id));
      }
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '反馈失败');
    }
  };

  return (
    <div style={{ display: 'flex', gap: 16, height: 'calc(100vh - 104px)' }}>
      {/* 聊天主区 */}
      <Card
        style={{ flex: 1, minWidth: 0, borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)', display: 'flex', flexDirection: 'column' }}
        styles={{ body: { display: 'flex', flexDirection: 'column', height: '100%', padding: 0 } }}
      >
        {/* 顶部工具行 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '12px 16px',
            borderBottom: '1px solid #F3F4F6',
            flexWrap: 'wrap',
          }}
        >
          <Select
            style={{ minWidth: 200 }}
            placeholder="会话列表"
            value={sessionId ?? undefined}
            onChange={(v) => void loadSession(v)}
            options={sessions.map((s) => ({
              value: s.id,
              label: `${s.id.slice(0, 8)} · ${s.status}`,
            }))}
          />
          <Button icon={<PlusOutlined />} onClick={startNewSession}>
            新建会话
          </Button>
          <Select
            mode="multiple"
            style={{ minWidth: 220 }}
            placeholder="选择知识库"
            value={kbIds}
            onChange={setKbIds}
            disabled={Boolean(sessionId)}
            options={knowledgeBases.map((kb) => ({ value: kb.id, label: kb.name }))}
            maxTagCount="responsive"
          />
          <div style={{ flex: 1 }} />
          {isAdmin && (
            <Select
              style={{ minWidth: 180 }}
              placeholder="模型"
              value={selectedModel ?? undefined}
              onChange={setSelectedModel}
              options={modelProfiles.map((p) => ({
                value: p.id,
                label: `${p.name} · ${p.model}${p.is_default ? '（默认）' : ''}`,
              }))}
            />
          )}
        </div>

        {/* 消息区 */}
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          style={{ flex: 1, overflowY: 'auto', padding: 20, background: '#F5F6FA' }}
        >
          {messages.length === 0 && !initializing ? (
            <div style={{ textAlign: 'center', marginTop: 80 }}>
              <Avatar size={64} icon={<RobotOutlined />} style={{ background: '#3B82F6' }} />
              <Typography.Title level={4} style={{ marginTop: 16 }}>
                你好，我是 AI 智能客服
              </Typography.Title>
              <Typography.Paragraph type="secondary">
                可回答退换货、退款、物流等问题；投诉或无法解答时自动转人工并生成工单。
              </Typography.Paragraph>
              <Space wrap>
                {QUICK_QUESTIONS.map((q) => (
                  <Button key={q} onClick={() => void sendMessage(q)}>
                    {q}
                  </Button>
                ))}
              </Space>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 760, margin: '0 auto' }}>
              {messages.map((m, idx) => {
                if (m.role === 'system') {
                  return (
                    <div key={m.id} style={{ textAlign: 'center' }}>
                      <span
                        style={{
                          display: 'inline-block',
                          background: '#F9FAFB',
                          border: '1px dashed #E5E7EB',
                          color: '#6B7280',
                          fontSize: 13,
                          borderRadius: 10,
                          padding: '6px 12px',
                        }}
                      >
                        {m.content}
                      </span>
                    </div>
                  );
                }
                const isUser = m.role === 'user';
                return (
                  <div
                    key={m.id}
                    style={{
                      display: 'flex',
                      gap: 10,
                      justifyContent: isUser ? 'flex-end' : 'flex-start',
                    }}
                  >
                    {!isUser && (
                      <Avatar size={32} icon={<RobotOutlined />} style={{ background: '#9CA3AF', flexShrink: 0 }} />
                    )}
                    <div style={{ maxWidth: '70%' }}>
                      <div
                        style={{
                          background: isUser ? '#3B82F6' : '#FFFFFF',
                          color: isUser ? '#FFFFFF' : '#1F2937',
                          borderRadius: 12,
                          padding: '10px 14px',
                          lineHeight: 1.7,
                          fontSize: 14,
                          boxShadow: isUser ? 'none' : '0 1px 3px rgba(0,0,0,.06)',
                          whiteSpace: 'pre-wrap',
                        }}
                      >
                        {renderWithRefs(m.content, scrollToCitation)}
                        {m.stopped && (
                          <span style={{ color: '#9CA3AF', marginLeft: 6 }}>（已停止）</span>
                        )}
                        {streaming && idx === messages.length - 1 && (
                          <span className="stream-cursor">▍</span>
                        )}
                      </div>
                      {m.form && !m.formSubmitted && (
                        <FormCard
                          form={m.form}
                          submitted={false}
                          onSubmit={(values) => void sendMessage('已填写表单', values)}
                        />
                      )}
                    </div>
                    {isUser && (
                      <Avatar size={32} icon={<UserOutlined />} style={{ background: '#3B82F6', flexShrink: 0 }} />
                    )}
                  </div>
                );
              })}
            </div>
          )}
          {initializing && (
            <div style={{ textAlign: 'center', marginTop: 100 }}>
              <Spin />
            </div>
          )}
        </div>

        {/* 输入区（03 §4.3） */}
        <div style={{ borderTop: '1px solid #F3F4F6', padding: '12px 16px', background: '#FFFFFF' }}>
          <Input.TextArea
            value={input}
            placeholder="请输入您的问题…（Enter 发送，Shift+Enter 换行）"
            autoSize={{ minRows: 1, maxRows: 4 }}
            maxLength={500}
            disabled={streaming}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void sendMessage(input);
              }
            }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
            {streaming ? (
              <Button danger icon={<StopOutlined />} onClick={stopGenerating}>
                停止
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<SendOutlined />}
                disabled={!input.trim()}
                onClick={() => void sendMessage(input)}
              >
                发送
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* 右侧知识引用面板（03 §4.4） */}
      <div
        style={{
          width: 320,
          flexShrink: 0,
          background: '#FFFFFF',
          borderRadius: 14,
          boxShadow: '0 1px 3px rgba(0,0,0,.06)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            padding: '14px 16px',
            borderBottom: '1px solid #F3F4F6',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <Typography.Text strong>知识引用</Typography.Text>
          {citations.length > 0 && (
            <Button
              type="link"
              size="small"
              onClick={() => setAddCitationOpen(true)}
            >
              补充引用
            </Button>
          )}
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
          {citations.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="本次回答未引用知识库内容"
            />
          ) : (
            citations.map((c, idx) => (
              <div
                key={c.chunk_id}
                id={`citation-${idx + 1}`}
                style={{
                  border: '1px solid #E5E7EB',
                  borderRadius: 10,
                  padding: 10,
                  marginBottom: 10,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography.Text strong style={{ fontSize: 13 }}>
                    [{idx + 1}] {c.document_name}
                  </Typography.Text>
                </div>
                <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>
                  {kbNameMap[c.kb_id] ?? '知识库'}
                  {c.page ? ` · ${c.page}` : ''}
                  {c.row ? ` 行 ${c.row}` : ''}
                </div>
                <Typography.Paragraph
                  style={{ fontSize: 12, marginTop: 6, marginBottom: 6, color: '#4B5563' }}
                  ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
                >
                  {c.answer}
                </Typography.Paragraph>
                <Space size={6} wrap>
                  <Tag color={scoreColor(c.retrieval_score)}>检索 {c.retrieval_score}%</Tag>
                  {c.rerank_score != null && (
                    <Tag color="purple">重排 {c.rerank_score.toFixed(4)}</Tag>
                  )}
                  <Popconfirm
                    title="删除该引用？"
                    onConfirm={() => void sendFeedback('delete', c)}
                  >
                    <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                      删除
                    </Button>
                  </Popconfirm>
                  <Popover
                    trigger="click"
                    content={
                      <div style={{ width: 240 }}>
                        <Input.TextArea
                          rows={2}
                          placeholder="标记无效原因（可选）"
                          id={`invalid-reason-${c.chunk_id}`}
                        />
                        <Button
                          type="primary"
                          size="small"
                          style={{ marginTop: 8 }}
                          onClick={() => {
                            const el = document.getElementById(
                              `invalid-reason-${c.chunk_id}`,
                            ) as HTMLTextAreaElement | null;
                            void sendFeedback('invalid', c, el?.value || undefined);
                          }}
                        >
                          确认
                        </Button>
                      </div>
                    }
                  >
                    <Button type="link" size="small">
                      标记无效
                    </Button>
                  </Popover>
                </Space>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 补充引用弹窗（B4 简化：候选池为当前引用列表） */}
      <Modal
        title="补充引用"
        open={addCitationOpen}
        onCancel={() => setAddCitationOpen(false)}
        footer={null}
        width={420}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="B4 简化：候选池为当前回答的引用列表；完整候选接口后续版本提供。"
        />
        {citations.map((c) => (
          <div
            key={c.chunk_id}
            style={{
              border: '1px solid #E5E7EB',
              borderRadius: 8,
              padding: 8,
              marginBottom: 8,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span style={{ fontSize: 13 }}>{c.question}</span>
            <Button
              type="link"
              size="small"
              onClick={() => {
                void sendFeedback('add', c);
                setAddCitationOpen(false);
              }}
            >
              补充
            </Button>
          </div>
        ))}
      </Modal>
    </div>
  );
}
