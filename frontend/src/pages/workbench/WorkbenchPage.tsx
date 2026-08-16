/** 客服工作台（13 §2）：三栏布局（队列/对话/工单信息），SSE 实时联动。 */

import {
  Badge,
  Button,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
  message,
} from 'antd';
import { LogoutOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import ChatConversation from '../../components/chat/ChatConversation';
import type { DisplayMessage } from '../../components/chat/types';
import { ApiError } from '../../api/client';
import {
  claimTicket,
  closeTicket,
  getAgentStatus,
  getAgentTicket,
  listAgentTickets,
  markAgentSessionRead,
  replyTicket,
  releaseTicket,
  setAgentStatus,
  type AgentTicketItem,
  type AgentTicketDetail,
} from '../../api/agent';
import { useAuthStore } from '../../stores/auth';
import { connectEventStream } from '../../utils/eventStream';

const STATUS_LABELS: Record<string, string> = {
  open: '待处理',
  processing: '处理中',
  closed: '已关闭',
};

const PRIORITY_COLORS: Record<string, string> = {
  high: 'red',
  medium: 'orange',
  low: 'default',
};

const FILTER_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'open', label: '待处理' },
  { value: 'processing', label: '处理中' },
  { value: 'closed', label: '已关闭' },
];

export default function WorkbenchPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const isAdminReadonly = user?.role === 'admin';

  const [filter, setFilter] = useState('open');
  const [mine, setMine] = useState(false);
  const [online, setOnline] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AgentTicketDetail | null>(null);
  const [replyText, setReplyText] = useState('');
  const [closeOpen, setCloseOpen] = useState(false);
  const [closeReason, setCloseReason] = useState('');
  const [releaseOpen, setReleaseOpen] = useState(false);
  const [releaseReason, setReleaseReason] = useState('');
  const [connLost, setConnLost] = useState(false);

  const { data: tickets, isLoading } = useQuery({
    queryKey: ['agent-tickets', filter, mine],
    queryFn: () => listAgentTickets({ status: filter, mine, page: 1, page_size: 100 }),
  });

  useEffect(() => {
    void getAgentStatus()
      .then((s) => setOnline(s.online))
      .catch(() => undefined);
  }, []);

  const invalidateAll = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['agent-tickets'] });
    void queryClient.invalidateQueries({ queryKey: ['overview'] });
  }, [queryClient]);

  const loadDetail = useCallback(
    async (id: string) => {
      try {
        const d = await getAgentTicket(id);
        setSelectedId(id);
        setDetail(d);
        const lastId = d.messages[d.messages.length - 1]?.id ?? null;
        void markAgentSessionRead(d.ticket.session_id, lastId);
        invalidateAll();
    } catch (err) {
      // 认领竞态等导致的 403：提示后刷新队列，避免停留在不可见工单
      if (err instanceof ApiError && err.code === 40300) {
        invalidateAll();
      }
      message.error(err instanceof ApiError ? err.message : '加载工单失败');
    }
    },
    [invalidateAll],
  );

  // 实时事件（scope=agent，13 §4）
  useEffect(() => {
    const off = connectEventStream(
      '/api/stream/events?scope=agent',
      {
        'ticket.created': () => {
          invalidateAll();
          if (filter === 'open') message.info('有新工单待处理');
        },
        'ticket.claimed': () => invalidateAll(),
        'ticket.closed': () => invalidateAll(),
        'ticket.updated': () => invalidateAll(),
        'message.new': (data) => {
          const sessionId = data.session_id as string | undefined;
          if (detail && sessionId === detail.ticket.session_id && selectedId) {
            void loadDetail(selectedId);
          } else {
            invalidateAll();
          }
        },
      },
      {
        onOpen: () => setConnLost(false),
        onError: () => setConnLost(true),
        onReconnect: () => {
          setConnLost(false);
          invalidateAll();
          if (selectedId) void loadDetail(selectedId);
        },
      },
    );
    return off;
  }, [detail, selectedId, filter, invalidateAll, loadDetail]);

  const claimMutation = useMutation({
    mutationFn: (id: string) => claimTicket(id),
    onSuccess: (res) => {
      message.success(`已认领 ${res.ticket_no}`);
      invalidateAll();
      if (res.id) void loadDetail(res.id);
    },
    onError: (err) => {
      // 40900：已被其他客服认领 → 提示并刷新队列（13 §2.3）
      message.error(err instanceof ApiError ? err.message : '认领失败');
      invalidateAll();
    },
  });

  const replyMutation = useMutation({
    mutationFn: () => replyTicket(selectedId!, replyText),
    onSuccess: () => {
      setReplyText('');
      if (selectedId) void loadDetail(selectedId);
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '回复失败'),
  });

  const closeMutation = useMutation({
    mutationFn: () => closeTicket(selectedId!, closeReason),
    onSuccess: () => {
      message.success('工单已关闭');
      setCloseOpen(false);
      setCloseReason('');
      setSelectedId(null);
      setDetail(null);
      invalidateAll();
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '关闭失败'),
  });

  const releaseMutation = useMutation({
    mutationFn: () => releaseTicket(selectedId!, releaseReason),
    onSuccess: () => {
      message.success('工单已释放回待处理，其他客服可认领');
      setReleaseOpen(false);
      setReleaseReason('');
      setSelectedId(null);
      setDetail(null);
      invalidateAll();
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '释放失败'),
  });

  const messages: DisplayMessage[] = useMemo(
    () =>
      (detail?.messages ?? []).map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        created_at: m.created_at,
        citations: m.citations?.map((c) => ({
          document_name: c.document_name,
          question: c.question,
          answer: c.answer,
          page: c.page,
          row: c.row,
          retrieval_score: c.retrieval_score,
          rerank_score: c.rerank_score,
        })),
      })),
    [detail],
  );

  const canHandle = Boolean(
    detail &&
      (user?.role === 'admin' ||
        detail.ticket.assignee_id === user?.id ||
        detail.ticket.status === 'open'),
  );

  return (
    <div
      style={{
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        background: '#fff',
        position: 'relative',
      }}
    >
      {/* 顶部栏 */}
      <div
        style={{
          height: 56,
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          padding: '0 16px',
          borderBottom: '1px solid #E5E7EB',
        }}
      >
        <Typography.Text strong style={{ fontSize: 16 }}>
          客服工作台
        </Typography.Text>
        <Select
          value={filter}
          onChange={(v) => {
            setFilter(v);
            setSelectedId(null);
            setDetail(null);
          }}
          options={FILTER_OPTIONS}
          style={{ width: 130 }}
        />
        <Switch
          checked={mine}
          onChange={setMine}
          checkedChildren="我负责的"
          unCheckedChildren="全部"
        />
        <span style={{ marginLeft: 'auto' }} />
        {connLost && <Typography.Text type="warning">实时连接断开，重连中…</Typography.Text>}
        {!isAdminReadonly && (
          <Space size={4}>
            <span>在线</span>
            <Switch
              checked={online}
              onChange={(v) => {
                setOnline(v);
                void setAgentStatus(v).catch(() => undefined);
              }}
              size="small"
            />
          </Space>
        )}
        <Button
          icon={<LogoutOutlined />}
          onClick={() => {
            logout();
            navigate('/login');
          }}
        >
          退出
        </Button>
      </div>

      {/* 三栏内容区 */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {isAdminReadonly && (
          <div
            style={{
              position: 'absolute',
              top: 56,
              left: 0,
              right: 0,
              zIndex: 5,
              textAlign: 'center',
              background: '#FFF7E6',
              color: '#D46B08',
              fontSize: 12,
              padding: '4px 0',
            }}
          >
            管理员只读模式：工单处理（认领/回复/关闭）请使用客服账号在客服工作台完成
          </div>
        )}
        {/* 左栏：工单队列 */}
        <div style={{ width: 300, borderRight: '1px solid #E5E7EB', overflow: 'auto', padding: 8 }}>
          {isLoading ? (
            <div style={{ padding: 20, textAlign: 'center' }}>加载中…</div>
          ) : (tickets?.items ?? []).length === 0 ? (
            <div style={{ padding: 20, textAlign: 'center', color: '#9CA3AF' }}>暂无工单</div>
          ) : (
            (tickets?.items ?? []).map((t: AgentTicketItem) => (
              <div
                key={t.id}
                onClick={() => void loadDetail(t.id)}
                style={{
                  padding: '10px 12px',
                  borderRadius: 8,
                  cursor: 'pointer',
                  marginBottom: 6,
                  background: t.id === selectedId ? '#EFF6FF' : '#F9FAFB',
                  border: t.id === selectedId ? '1px solid #BFDBFE' : '1px solid transparent',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography.Text strong style={{ fontSize: 13 }}>
                    {t.ticket_no}
                  </Typography.Text>
                  <Badge count={t.unread_count} size="small" />
                </div>
                <div style={{ display: 'flex', gap: 6, marginTop: 4, alignItems: 'center' }}>
                  <Tag color={PRIORITY_COLORS[t.priority]} style={{ marginRight: 0 }}>
                    {t.priority === 'high' ? '高' : t.priority === 'medium' ? '中' : '低'}
                  </Tag>
                  <Tag
                    color={t.status === 'open' ? 'orange' : t.status === 'processing' ? 'blue' : 'default'}
                    style={{ marginRight: 0 }}
                  >
                    {STATUS_LABELS[t.status]}
                  </Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 'auto' }}>
                    {dayjs(t.last_message_at ?? t.created_at).format('HH:mm')}
                  </Typography.Text>
                </div>
                <div style={{ fontSize: 12, color: '#6B7280', marginTop: 4 }}>
                  {t.user_name || '匿名用户'} · {(t.last_message || '暂无消息').slice(0, 30)}
                </div>
              </div>
            ))
          )}
        </div>

        {/* 中栏：对话 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <div style={{ flex: 1, overflow: 'auto', background: '#F9FAFB' }}>
            {detail ? (
              <ChatConversation messages={messages} />
            ) : (
              <div style={{ textAlign: 'center', color: '#9CA3AF', padding: 60 }}>
                选择左侧工单开始处理
              </div>
            )}
          </div>
          {detail && !isAdminReadonly && (
            <div style={{ padding: 12, borderTop: '1px solid #E5E7EB' }}>
              <Input.TextArea
                value={replyText}
                onChange={(e) => setReplyText(e.target.value.slice(0, 2000))}
                placeholder="回复用户（Enter 发送，Shift+Enter 换行）"
                autoSize={{ minRows: 2, maxRows: 5 }}
                disabled={!canHandle || detail.ticket.status === 'closed'}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (replyText.trim()) replyMutation.mutate();
                  }
                }}
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                <Button
                  type="primary"
                  disabled={!canHandle || !replyText.trim() || detail.ticket.status === 'closed'}
                  loading={replyMutation.isPending}
                  onClick={() => replyMutation.mutate()}
                >
                  发送回复
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* 右栏：工单信息 */}
        <div style={{ width: 300, borderLeft: '1px solid #E5E7EB', overflow: 'auto', padding: 16 }}>
          {detail ? (
            <>
              <Typography.Text strong>{detail.ticket.ticket_no}</Typography.Text>
              <div style={{ margin: '10px 0' }}>
                <Space wrap>
                  <Tag
                    color={detail.ticket.status === 'open' ? 'orange' : detail.ticket.status === 'processing' ? 'blue' : 'default'}
                  >
                    {STATUS_LABELS[detail.ticket.status]}
                  </Tag>
                  <Tag color={PRIORITY_COLORS[detail.ticket.priority]}>
                    {detail.ticket.priority === 'high' ? '高' : detail.ticket.priority === 'medium' ? '中' : '低'}
                  </Tag>
                </Space>
              </div>
              <InfoRow label="创建时间" value={dayjs(detail.ticket.created_at).format('YYYY-MM-DD HH:mm')} />
              {detail.ticket.claimed_at && (
                <InfoRow label="认领时间" value={dayjs(detail.ticket.claimed_at).format('YYYY-MM-DD HH:mm')} />
              )}
              {detail.ticket.closed_at && (
                <InfoRow label="关闭时间" value={dayjs(detail.ticket.closed_at).format('YYYY-MM-DD HH:mm')} />
              )}
              {detail.ticket.close_reason && <InfoRow label="关闭原因" value={detail.ticket.close_reason} />}
              <InfoRow
                label="用户"
                value={detail.user ? `${detail.user.display_name}（${detail.user.username}）` : '匿名用户'}
              />
              <InfoRow label="诉求摘要" value={detail.ticket.content.slice(0, 120)} />
              {detail.rating && (
                <InfoRow
                  label="满意度"
                  value={`${detail.rating.score} 星${detail.rating.comment ? ` · ${detail.rating.comment}` : ''}`}
                />
              )}

              <div style={{ marginTop: 16 }}>
                {!isAdminReadonly && detail.ticket.status === 'open' && (
                  <Button
                    type="primary"
                    block
                    loading={claimMutation.isPending}
                    onClick={() => claimMutation.mutate(detail.ticket.id)}
                  >
                    认领工单
                  </Button>
                )}
                {!isAdminReadonly && detail.ticket.status === 'processing' && canHandle && (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Button danger block onClick={() => setCloseOpen(true)}>
                      关闭工单
                    </Button>
                    <Button block onClick={() => setReleaseOpen(true)}>
                      释放工单
                    </Button>
                  </Space>
                )}
              </div>

              {detail.notes.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <Typography.Text strong>处理记录</Typography.Text>
                  {detail.notes.map((n) => (
                    <div key={n.id} style={{ fontSize: 12, color: '#6B7280', marginTop: 6 }}>
                      {dayjs(n.created_at).format('MM-DD HH:mm')} {n.operator}：{n.note}
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <Typography.Text type="secondary">选择工单后显示详情</Typography.Text>
          )}
        </div>
      </div>

      {/* 关闭工单：原因必填 */}
      <Modal
        title="关闭工单"
        open={closeOpen}
        onCancel={() => setCloseOpen(false)}
        onOk={() => {
          if (!closeReason.trim()) {
            message.warning('请填写关闭原因');
            return;
          }
          closeMutation.mutate();
        }}
        confirmLoading={closeMutation.isPending}
      >
        <Input.TextArea
          value={closeReason}
          onChange={(e) => setCloseReason(e.target.value.slice(0, 200))}
          placeholder="关闭原因（必填）：已解决 / 用户放弃 / 重复工单 / 其他"
          rows={3}
        />
      </Modal>

      {/* 释放工单：处理中 → 待处理（assignee/admin 可用） */}
      <Modal
        title="释放工单"
        open={releaseOpen}
        onCancel={() => setReleaseOpen(false)}
        onOk={() => releaseMutation.mutate()}
        confirmLoading={releaseMutation.isPending}
      >
        <p style={{ color: '#6B7280', marginTop: 0 }}>
          释放后工单回到「待处理」队列，任何客服都可重新认领。仅负责人或管理员可操作。
        </p>
        <Input.TextArea
          value={releaseReason}
          onChange={(e) => setReleaseReason(e.target.value.slice(0, 200))}
          placeholder="释放原因（可选）"
          rows={2}
        />
      </Modal>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ fontSize: 13, margin: '8px 0' }}>
      <span style={{ color: '#9CA3AF', marginRight: 8 }}>{label}</span>
      <span style={{ color: '#374151' }}>{value}</span>
    </div>
  );
}
