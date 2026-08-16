/** 会话详情（10 §4.2–4.4 / sessions.html）：消息流 + 引用面板 + 链路 + 标注 + 关联工单。 */

import { ArrowLeftOutlined, RobotOutlined, UserOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Avatar,
  Button,
  Card,
  Empty,
  Input,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
  message,
} from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { ApiError } from '../../api/client';
import { listEvalSets } from '../../api/evaluation';
import { useAuthStore } from '../../stores/auth';
import {
  INTENT_LABELS,
  annotateSession,
  getSession,
} from '../../api/sessions';

export default function SessionDetailPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const isAgent = user?.role === 'agent';
  const [tags, setTags] = useState<string[]>([]);
  const [note, setNote] = useState('');
  const [includeInEval, setIncludeInEval] = useState(false);
  const [evalSetId, setEvalSetId] = useState<string | null>(null);

  const { data: detail, isLoading } = useQuery({
    queryKey: ['session-detail', id],
    queryFn: () => getSession(id),
    enabled: Boolean(id),
  });
  const { data: evalSets = [] } = useQuery({
    queryKey: ['eval-sets'],
    queryFn: listEvalSets,
    retry: false, // agent 可能无权限，失败静默
  });

  useEffect(() => {
    if (detail?.annotation) {
      setTags(detail.annotation.tags);
      setNote(detail.annotation.note);
      setIncludeInEval(detail.annotation.include_in_eval);
      setEvalSetId(detail.annotation.eval_set_id);
    }
  }, [detail]);

  const saveMutation = useMutation({
    mutationFn: () =>
      annotateSession(id, {
        tags,
        note,
        include_in_eval: includeInEval,
        // 职责分离（方案 C）：客服标注不指定评测集，仅产生候选由管理员确认
        eval_set_id: includeInEval && !isAgent ? evalSetId : null,
      }),
    onSuccess: () => {
      message.success('标注已保存');
      queryClient.invalidateQueries({ queryKey: ['session-detail', id] });
      queryClient.invalidateQueries({ queryKey: ['sessions-list'] });
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '保存失败'),
  });

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin />
      </div>
    );
  }
  if (!detail) return <Empty description="会话不存在" />;

  const allCitations = detail.messages.flatMap((m) =>
    (m.citations ?? []).map((c) => ({ ...c, messageId: m.id })),
  );

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/sessions')}>
          返回列表
        </Button>
        <Typography.Text strong className="num">{id.slice(0, 8)}…</Typography.Text>
        <Tag color={detail.session.status === 'transferred' ? 'red' : 'blue'}>
          {detail.session.status}
        </Tag>
        {detail.session.intent && (
          <Tag>{INTENT_LABELS[detail.session.intent] ?? detail.session.intent}</Tag>
        )}
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: '#9CA3AF' }}>
          {detail.session.created_at.replace('T', ' ').slice(0, 16)} 开始
        </span>
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        {/* 消息流 */}
        <Card style={{ flex: 1, minWidth: 0, borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: 8 }}>
            {detail.messages.map((m) => {
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
                  style={{ display: 'flex', gap: 10, justifyContent: isUser ? 'flex-end' : 'flex-start' }}
                >
                  {!isUser && (
                    <Avatar size={30} icon={<RobotOutlined />} style={{ background: '#9CA3AF', flexShrink: 0 }} />
                  )}
                  <div style={{ maxWidth: '72%' }}>
                    <div
                      style={{
                        background: isUser ? '#3B82F6' : '#F3F4F6',
                        color: isUser ? '#FFFFFF' : '#1F2937',
                        borderRadius: 12,
                        padding: '10px 14px',
                        lineHeight: 1.7,
                        fontSize: 14,
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {m.content}
                    </div>
                    <div style={{ fontSize: 12, color: '#9CA3AF', marginTop: 4 }}>
                      {m.created_at.slice(11, 16)}
                      {m.intent ? ` · ${INTENT_LABELS[m.intent] ?? m.intent}` : ''}
                    </div>
                  </div>
                  {isUser && (
                    <Avatar size={30} icon={<UserOutlined />} style={{ background: '#3B82F6', flexShrink: 0 }} />
                  )}
                </div>
              );
            })}
          </div>
        </Card>

        {/* 右侧面板 */}
        <div style={{ width: 340, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card size="small" title={`知识引用（${allCitations.length}）`} style={{ borderRadius: 14 }}>
            {allCitations.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本次回答未引用知识库内容" />
            ) : (
              allCitations.map((c, i) => (
                <div
                  key={c.chunk_id}
                  id={`citation-${i + 1}`}
                  style={{ border: '1px solid #E5E7EB', borderRadius: 10, padding: 10, marginBottom: 8 }}
                >
                  <div style={{ fontSize: 13, fontWeight: 500 }}>
                    [{i + 1}] {c.document_name}
                  </div>
                  <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>{c.question}</div>
                  <Typography.Paragraph
                    style={{ fontSize: 12, marginTop: 4, marginBottom: 0, color: '#4B5563' }}
                    ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}
                  >
                    {c.answer}
                  </Typography.Paragraph>
                  <div style={{ fontSize: 12, color: '#9CA3AF', marginTop: 4 }}>
                    {c.row ? `行 ${c.row}` : ''}
                    {c.retrieval_score != null ? ` · 检索 ${c.retrieval_score}%` : ''}
                  </div>
                </div>
              ))
            )}
          </Card>

          <Card size="small" title="调用链路（trace）" style={{ borderRadius: 14 }}>
            {!detail.trace ? (
              <div style={{ color: '#9CA3AF', fontSize: 13 }}>该会话无链路日志</div>
            ) : (
              detail.trace.steps.map((s, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: 13,
                    padding: '6px 0',
                    borderBottom: '1px dashed #F3F4F6',
                  }}
                >
                  <span style={{ color: '#6B7280' }}>{s.step}</span>
                  <span className="num" style={{ color: '#9CA3AF' }}>
                    {s.latency_ms}ms
                  </span>
                </div>
              ))
            )}
          </Card>

          <Card size="small" title="人工标注" style={{ borderRadius: 14 }}>
            <div style={{ fontSize: 13, color: '#6B7280', marginBottom: 6 }}>标签（多选）</div>
            <Select
              mode="tags"
              style={{ width: '100%' }}
              placeholder="输入后回车添加"
              value={tags}
              onChange={setTags}
              tokenSeparators={[',', '，']}
              maxCount={10}
            />
            <div style={{ fontSize: 13, color: '#6B7280', margin: '10px 0 6px' }}>备注</div>
            <Input.TextArea
              rows={3}
              placeholder="补充说明…"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={500}
            />
            <div style={{ marginTop: 12 }}>
              <Space>
                <Switch checked={includeInEval} onChange={setIncludeInEval} />
                <span style={{ fontSize: 13 }}>纳入评测集</span>
              </Space>
              {includeInEval && (
                isAgent ? (
                  <div style={{ fontSize: 12, color: '#9CA3AF', marginTop: 8 }}>
                    客服标注将进入评测集候选，由管理员确认入集
                  </div>
                ) : (
                  <Select
                    style={{ width: '100%', marginTop: 8 }}
                    placeholder="选择目标评测集（可选）"
                    value={evalSetId ?? undefined}
                    onChange={setEvalSetId}
                    options={evalSets.map((s) => ({ value: s.id, label: `${s.name}（${s.sample_count}）` }))}
                  />
                )
              )}
            </div>
            <Button
              type="primary"
              block
              style={{ marginTop: 12 }}
              loading={saveMutation.isPending}
              onClick={() => saveMutation.mutate()}
            >
              保存标注
            </Button>
          </Card>

          {detail.ticket && (
            <Card size="small" title="关联工单" style={{ borderRadius: 14 }}>
              <Typography.Text strong className="num">
                {detail.ticket.ticket_no}
              </Typography.Text>
              <div style={{ fontSize: 12, color: '#9CA3AF', marginTop: 4 }}>
                状态 {detail.ticket.status} · 优先级 {detail.ticket.priority}
              </div>
              <Button
                type="link"
                size="small"
                style={{ paddingLeft: 0 }}
                onClick={() => navigate('/tickets')}
              >
                前往工单列表
              </Button>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
