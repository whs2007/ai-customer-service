/** 对话消息流（12 §4.2 / 13 §2.2）：用户右蓝、AI 左灰、人工左绿、系统居中灰字。 */

import { CaretRightOutlined } from '@ant-design/icons';
import { Collapse, Tag, Typography } from 'antd';
import { useEffect, useRef } from 'react';

import type { DisplayMessage } from './types';

export default function ChatConversation({ messages }: { messages: DisplayMessage[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div style={{ textAlign: 'center', color: '#9CA3AF', padding: 40 }}>
        暂无消息，输入下方问题开始咨询
      </div>
    );
  }

  return (
    <div style={{ padding: 16 }}>
      {messages.map((m) => {
        if (m.role === 'system') {
          return (
            <div key={m.id} style={{ textAlign: 'center', margin: '10px 0' }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {m.content}
              </Typography.Text>
            </div>
          );
        }
        const isUser = m.role === 'user';
        const isAgent = m.role === 'agent';
        const bubbleStyle: React.CSSProperties = {
          maxWidth: '72%',
          padding: '10px 14px',
          borderRadius: 12,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          background: isUser ? '#3B82F6' : isAgent ? '#10B981' : '#F3F4F6',
          color: isUser ? '#fff' : '#1F2937',
        };
        return (
          <div
            key={m.id}
            style={{
              display: 'flex',
              justifyContent: isUser ? 'flex-end' : 'flex-start',
              margin: '10px 0',
            }}
          >
            <div style={{ maxWidth: '76%' }}>
              <div style={bubbleStyle}>
                {isAgent && (
                  <Tag color="green" style={{ marginRight: 6 }}>
                    人工客服
                  </Tag>
                )}
                {m.content || (m.role === 'assistant' ? '…' : '')}
              </div>
              {m.citations && m.citations.length > 0 && (
                <Collapse
                  ghost
                  size="small"
                  style={{ marginTop: 4 }}
                  items={[
                    {
                      key: 'citations',
                      label: (
                        <span style={{ fontSize: 12, color: '#6B7280' }}>
                          来源：{m.citations.map((c) => c.document_name).join('、')}
                        </span>
                      ),
                      children: (
                        <div>
                          {m.citations.map((c, i) => (
                            <div key={i} style={{ fontSize: 12, color: '#4B5563', marginBottom: 6 }}>
                              <CaretRightOutlined style={{ marginRight: 4 }} />
                              <Typography.Text strong>{c.document_name}</Typography.Text>
                              {c.page != null && `（第 ${c.page} 页）`}
                              {c.row != null && `（第 ${c.row} 行）`}
                              {c.question ? <div style={{ margin: '2px 0' }}>问：{c.question}</div> : null}
                              {c.answer ? <div>答：{c.answer}</div> : null}
                              {c.retrieval_score != null && (
                                <div style={{ marginTop: 2 }}>
                                  检索分 {c.retrieval_score.toFixed(4)}
                                  {c.rerank_score != null ? ` / 重排分 ${c.rerank_score.toFixed(4)}` : ''}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      ),
                    },
                  ]}
                />
              )}
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
