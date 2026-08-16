/** 文件详情 / Chunk 管理（04 §4）：卡片列表 + 新增/编辑/删除。 */

import {
  ArrowLeftOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Breadcrumb,
  Button,
  Card,
  Empty,
  Modal,
  Pagination,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { useAuthStore } from '../../stores/auth';

import { ApiError } from '../../api/client';
import {
  createChunk,
  deleteChunk,
  getDocument,
  getKnowledgeBase,
  listChunks,
  updateChunk,
  type ChunkItem,
} from '../../api/knowledge';
import ChunkModal from './ChunkModal';

interface ChunkFormValues {
  question: string;
  answer: string;
  category?: string | null;
  tags?: string[];
  page?: string | null;
  row?: string | null;
}

export default function ChunkDetailPage() {
  const { kbId = '', docId = '' } = useParams();
  const queryClient = useQueryClient();
  // 职责分离（方案 B）：agent 只读 Chunk
  const readonly = useAuthStore((s) => s.user)?.role === 'agent';
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ChunkItem | null>(null);

  const { data: kb } = useQuery({
    queryKey: ['knowledge-base-detail', kbId],
    queryFn: () => getKnowledgeBase(kbId),
    enabled: Boolean(kbId),
  });
  const { data: doc } = useQuery({
    queryKey: ['document', docId],
    queryFn: () => getDocument(docId),
    enabled: Boolean(docId),
  });
  const { data, isLoading } = useQuery({
    queryKey: ['chunks', docId, page, pageSize],
    queryFn: () => listChunks(docId, { page, page_size: pageSize }),
    enabled: Boolean(docId),
    placeholderData: (prev) => prev,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['chunks', docId] });
    queryClient.invalidateQueries({ queryKey: ['document', docId] });
  };

  const saveMutation = useMutation({
    mutationFn: (values: ChunkFormValues) =>
      editing ? updateChunk(editing.id, values) : createChunk({ doc_id: docId, ...values }),
    onSuccess: () => {
      message.success(editing ? '已更新，正在重新向量化' : '已添加 Chunk');
      setModalOpen(false);
      invalidate();
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '保存失败'),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteChunk,
    onSuccess: () => {
      message.success('删除成功');
      invalidate();
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '删除失败'),
  });

  const confirmDelete = (chunk: ChunkItem) => {
    Modal.confirm({
      title: '删除 Chunk',
      content: `确定删除「${chunk.question}」吗？删除后该切片将不可恢复。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => deleteMutation.mutateAsync(chunk.id),
    });
  };

  const chunks = useMemo(() => data?.items ?? [], [data]);

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => window.history.back()}>
          返回
        </Button>
        <Breadcrumb
          items={[
            { title: <Link to="/knowledge">知识库</Link> },
            { title: <Link to={`/knowledge/${kbId}`}>{kb?.name ?? '...'}</Link> },
            { title: doc?.file_name ?? '...' },
          ]}
        />
      </div>

      <Card
        style={{ borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}
        title={
          <Space>
            <span>Chunk 列表</span>
            {doc && (
              <Tag color={doc.status === 'completed' ? 'green' : 'blue'}>{doc.status}</Tag>
            )}
            {doc && doc.status === 'failed' && (
              <Typography.Text type="danger" style={{ fontSize: 12 }}>
                {doc.error_message}
              </Typography.Text>
            )}
          </Space>
        }
        extra={
          !readonly ? (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}>
              添加 Chunk
            </Button>
          ) : undefined
        }
      >
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin />
          </div>
        ) : chunks.length === 0 ? (
          <Empty
            description="暂无 Chunk，请重新解析文档或手动添加"
          />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {chunks.map((chunk) => (
              <Card
                key={chunk.id}
                size="small"
                style={{ borderRadius: 10, borderColor: '#E5E7EB' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <Typography.Text strong>
                      Chunk {chunk.chunk_index} · {chunk.question}
                    </Typography.Text>
                    <div style={{ marginTop: 8, whiteSpace: 'pre-wrap', fontSize: 14, color: '#374151', lineHeight: 1.7 }}>
                      {chunk.answer}
                    </div>
                    <div style={{ marginTop: 10, display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 12, color: '#6B7280' }}>
                      {chunk.category && <span>分类：{chunk.category}</span>}
                      {(chunk.page || chunk.row) && (
                        <span>
                          来源：{chunk.page ? `${chunk.page}` : ''}
                          {chunk.row ? ` 行 ${chunk.row}` : ''}
                        </span>
                      )}
                      <span className="num">{chunk.word_count} 字</span>
                      {chunk.tags.map((tag) => (
                        <Tag key={tag} style={{ marginInlineEnd: 4 }}>
                          {tag}
                        </Tag>
                      ))}
                    </div>
                  </div>
                  {!readonly && (
                    <Space>
                      <Button
                        type="link"
                        size="small"
                        icon={<EditOutlined />}
                        onClick={() => {
                          setEditing(chunk);
                          setModalOpen(true);
                        }}
                      >
                        编辑
                      </Button>
                      <Button
                        type="link"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => confirmDelete(chunk)}
                      >
                        删除
                      </Button>
                    </Space>
                  )}
                </div>
              </Card>
            ))}
            {(data?.total ?? 0) > 0 && (
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <Pagination
                  current={page}
                  pageSize={pageSize}
                  total={data?.total ?? 0}
                  showTotal={(total) => `共 ${total} 条`}
                  showSizeChanger
                  pageSizeOptions={[10, 20, 50]}
                  onChange={(p, ps) => {
                    setPage(p);
                    setPageSize(ps);
                  }}
                />
              </div>
            )}
          </div>
        )}
      </Card>

      <ChunkModal
        open={modalOpen}
        editing={editing}
        submitting={saveMutation.isPending}
        onCancel={() => setModalOpen(false)}
        onSubmit={(values) => saveMutation.mutate(values)}
      />
    </div>
  );
}
