/** 知识库页布局（04 §1.3）：左侧知识库列表 + 右侧内容区。 */

import {
  DeleteOutlined,
  EditOutlined,
  FolderFilled,
  PlusOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Empty,
  List,
  Modal,
  Skeleton,
  Typography,
  message,
} from 'antd';
import { useState } from 'react';
import { Outlet, useNavigate, useParams } from 'react-router-dom';

import { ApiError } from '../../api/client';
import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  listKnowledgeBases,
  updateKnowledgeBase,
  type KnowledgeBase,
} from '../../api/knowledge';
import KnowledgeBaseModal from './KnowledgeBaseModal';

export default function KnowledgeLayout() {
  const navigate = useNavigate();
  const { kbId } = useParams();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<KnowledgeBase | null>(null);

  const { data: knowledgeBases = [], isLoading } = useQuery({
    queryKey: ['knowledge-bases'],
    queryFn: listKnowledgeBases,
  });

  const createMutation = useMutation({
    mutationFn: createKnowledgeBase,
    onSuccess: (kb) => {
      message.success('创建成功');
      setModalOpen(false);
      queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] });
      navigate(`/knowledge/${kb.id}`);
    },
    onError: (err) => {
      message.error(err instanceof ApiError ? err.message : '创建失败');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, values }: { id: string; values: { name: string; description: string } }) =>
      updateKnowledgeBase(id, values),
    onSuccess: () => {
      message.success('更新成功');
      setModalOpen(false);
      queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] });
      queryClient.invalidateQueries({ queryKey: ['knowledge-base-detail'] });
    },
    onError: (err) => {
      message.error(err instanceof ApiError ? err.message : '更新失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteKnowledgeBase,
    onSuccess: () => {
      message.success('删除成功');
      queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] });
      if (kbId) {
        navigate('/knowledge');
      }
    },
    onError: (err) => {
      message.error(err instanceof ApiError ? err.message : '删除失败');
    },
  });

  const confirmDelete = (kb: KnowledgeBase) => {
    Modal.confirm({
      title: '删除知识库',
      content: '删除后将同时删除其中所有文档与切片，且不可恢复。确定删除吗？',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => deleteMutation.mutateAsync(kb.id),
    });
  };

  const onSubmit = (values: { name: string; description: string }) => {
    if (editing) {
      updateMutation.mutate({ id: editing.id, values });
    } else {
      createMutation.mutate(values);
    }
  };

  return (
    <div style={{ display: 'flex', gap: 16, minHeight: 'calc(100vh - 104px)' }}>
      {/* 左侧知识库列表（宽 240） */}
      <div
        style={{
          width: 240,
          flexShrink: 0,
          background: '#FFFFFF',
          borderRadius: 14,
          boxShadow: '0 1px 3px rgba(0,0,0,.06)',
          padding: '16px 12px',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 12,
            padding: '0 8px',
          }}
        >
          <Typography.Text strong style={{ fontSize: 15 }}>
            知识库
          </Typography.Text>
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}
          >
            创建
          </Button>
        </div>
        {isLoading ? (
          <Skeleton active paragraph={{ rows: 5 }} />
        ) : knowledgeBases.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <span style={{ fontSize: 12, color: '#9CA3AF' }}>暂无知识库，点击上方创建</span>
            }
          />
        ) : (
          <List
            dataSource={knowledgeBases}
            style={{ overflowY: 'auto' }}
            renderItem={(kb) => {
              const active = kb.id === kbId;
              return (
                <List.Item
                  key={kb.id}
                  onClick={() => navigate(`/knowledge/${kb.id}`)}
                  style={{
                    cursor: 'pointer',
                    padding: '10px 12px',
                    borderRadius: 10,
                    border: 'none',
                    background: active ? '#EFF6FF' : 'transparent',
                    color: active ? '#2563EB' : '#1F2937',
                    borderLeft: active ? '3px solid #3B82F6' : '3px solid transparent',
                  }}
                  actions={
                    active
                      ? [
                          <EditOutlined
                            key="edit"
                            onClick={(e) => {
                              e.stopPropagation();
                              setEditing(kb);
                              setModalOpen(true);
                            }}
                          />,
                          <DeleteOutlined
                            key="delete"
                            style={{ color: '#EF4444' }}
                            onClick={(e) => {
                              e.stopPropagation();
                              confirmDelete(kb);
                            }}
                          />,
                        ]
                      : undefined
                  }
                >
                  <List.Item.Meta
                    avatar={<FolderFilled style={{ color: active ? '#3B82F6' : '#9CA3AF' }} />}
                    title={
                      <span style={{ fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>
                        {kb.name}
                      </span>
                    }
                    description={<span style={{ fontSize: 12 }}>{kb.doc_count} 个文档</span>}
                  />
                </List.Item>
              );
            }}
          />
        )}
      </div>

      {/* 右侧内容区 */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <Outlet />
      </div>

      <KnowledgeBaseModal
        open={modalOpen}
        editing={editing}
        submitting={createMutation.isPending || updateMutation.isPending}
        onCancel={() => setModalOpen(false)}
        onSubmit={onSubmit}
      />
    </div>
  );
}

