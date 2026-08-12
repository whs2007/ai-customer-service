/** 知识库文档列表（04 §3）：搜索、上传、状态轮询、删除、重新解析。 */

import {
  ArrowLeftOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  EyeOutlined,
  FileExcelOutlined,
  FileImageOutlined,
  FileTextOutlined,
  FileUnknownOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Empty,
  Input,
  Modal,
  Pagination,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
  type UploadProps,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { ApiError } from '../../api/client';
import {
  deleteDocument,
  getKnowledgeBase,
  listDocuments,
  reparseDocument,
  uploadDocument,
  type DocumentItem,
} from '../../api/knowledge';

const PROCESSING_STATUSES = ['uploading', 'parsing', 'embedding'];
const ALLOWED_EXTENSIONS = ['.xlsx', '.csv', '.md', '.txt', '.pdf', '.docx'];
const MAX_SIZE = 20 * 1024 * 1024;

const STATUS_TAG: Record<DocumentItem['status'], { color: string; label: string }> = {
  uploading: { color: 'blue', label: '上传中' },
  parsing: { color: 'blue', label: '解析中' },
  embedding: { color: 'blue', label: '向量化中' },
  completed: { color: 'green', label: '已完成' },
  failed: { color: 'red', label: '失败' },
};

function fileIcon(fileType: string) {
  if (fileType === 'xlsx') return <FileExcelOutlined style={{ color: '#16A34A' }} />;
  if (['png', 'jpg', 'jpeg'].includes(fileType)) return <FileImageOutlined />;
  if (['md', 'txt', 'pdf', 'docx', 'csv'].includes(fileType))
    return <FileTextOutlined style={{ color: '#3B82F6' }} />;
  return <FileUnknownOutlined />;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function DocumentsPanel() {
  const { kbId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState('');
  const [debouncedKeyword, setDebouncedKeyword] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  // 搜索防抖 300ms（04 §3.4）
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedKeyword(keyword.trim()), 300);
    return () => clearTimeout(timer);
  }, [keyword]);

  const { data: kb } = useQuery({
    queryKey: ['knowledge-base-detail', kbId],
    queryFn: () => getKnowledgeBase(kbId),
    enabled: Boolean(kbId),
  });

  const { data, isLoading } = useQuery({
    queryKey: ['documents', kbId, debouncedKeyword, page, pageSize],
    queryFn: () =>
      listDocuments(kbId, {
        keyword: debouncedKeyword || undefined,
        page,
        page_size: pageSize,
      }),
    enabled: Boolean(kbId),
    placeholderData: (prev) => prev,
    refetchInterval: (query) => {
      const docs = query.state.data?.items ?? [];
      return docs.some((d) => PROCESSING_STATUSES.includes(d.status)) ? 2000 : false;
    },
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['documents', kbId] });
    queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] });
    queryClient.invalidateQueries({ queryKey: ['knowledge-base-detail'] });
  };

  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      message.success('删除成功');
      invalidate();
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '删除失败'),
  });

  const reparseMutation = useMutation({
    mutationFn: reparseDocument,
    onSuccess: () => {
      message.success('已开始重新解析');
      invalidate();
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '操作失败'),
  });

  const confirmDelete = (doc: DocumentItem) => {
    Modal.confirm({
      title: '删除文档',
      content: `将删除「${doc.file_name}」及其全部 Chunk 与向量，且不可恢复。确定删除吗？`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => deleteMutation.mutateAsync(doc.id),
    });
  };

  const columns: ColumnsType<DocumentItem> = useMemo(
    () => [
      {
        title: '文件名',
        dataIndex: 'file_name',
        ellipsis: true,
        render: (name: string, doc) => (
          <Space>
            {fileIcon(doc.file_type)}
            <Tooltip title={name}>
              <span style={{ color: '#1F2937' }}>{name}</span>
            </Tooltip>
          </Space>
        ),
      },
      {
        title: '类型',
        dataIndex: 'file_type',
        width: 90,
        render: (t: string) => <Tag>{t.toUpperCase()}</Tag>,
      },
      {
        title: '状态',
        dataIndex: 'status',
        width: 130,
        render: (status: DocumentItem['status']) => {
          const cfg = STATUS_TAG[status];
          return (
            <Tag color={cfg.color} icon={PROCESSING_STATUSES.includes(status) ? <Spin size="small" /> : undefined}>
              {cfg.label}
            </Tag>
          );
        },
      },
      {
        title: '大小',
        dataIndex: 'file_size',
        width: 110,
        render: (v: number) => <span className="num">{formatSize(v)}</span>,
      },
      {
        title: 'Chunk 数',
        dataIndex: 'chunk_count',
        width: 100,
        render: (v: number, doc) => (
          <Typography.Link
            className="num"
            onClick={() => navigate(`/knowledge/${kbId}/documents/${doc.id}`)}
          >
            {v}
          </Typography.Link>
        ),
      },
      {
        title: '操作',
        key: 'actions',
        width: 190,
        render: (_, doc) => (
          <Space size="middle">
            <Button
              type="link"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => navigate(`/knowledge/${kbId}/documents/${doc.id}`)}
            >
              查看详情
            </Button>
            {doc.status === 'failed' && (
              <Button
                type="link"
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => reparseMutation.mutate(doc.id)}
              >
                重新解析
              </Button>
            )}
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => confirmDelete(doc)}
            >
              删除
            </Button>
          </Space>
        ),
      },
    ],
    [kbId, navigate, reparseMutation],
  );

  const customRequest: UploadProps['customRequest'] = async (options) => {
    try {
      await uploadDocument(kbId, options.file as File, (percent) =>
        options.onProgress?.({ percent }),
      );
      message.success('上传成功，正在解析');
      options.onSuccess?.({});
      invalidate();
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '上传失败');
      options.onError?.(err instanceof Error ? err : new Error('上传失败'));
    }
  };

  return (
    <div
      style={{
        background: '#FFFFFF',
        borderRadius: 14,
        boxShadow: '0 1px 3px rgba(0,0,0,.06)',
        padding: 20,
      }}
    >
      {/* 工具行 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          marginBottom: 16,
          flexWrap: 'wrap',
        }}
      >
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/knowledge')}>
          返回
        </Button>
        <div style={{ minWidth: 0 }}>
          <Typography.Text strong style={{ fontSize: 16 }}>
            {kb?.name ?? '...'}
          </Typography.Text>
          {kb?.description && (
            <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
              {kb.description}
            </Typography.Text>
          )}
        </div>
        <div style={{ flex: 1 }} />
        <Input.Search
          placeholder="搜索文件名"
          allowClear
          style={{ width: 240 }}
          value={keyword}
          onChange={(e) => {
            setKeyword(e.target.value);
            setPage(1);
          }}
        />
        <Upload
          accept={ALLOWED_EXTENSIONS.join(',')}
          showUploadList={false}
          customRequest={customRequest}
          beforeUpload={(file) => {
            const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
            if (!ALLOWED_EXTENSIONS.includes(ext)) {
              message.error(`不支持的文件类型（支持：${ALLOWED_EXTENSIONS.join(' / ')}）`);
              return Upload.LIST_IGNORE;
            }
            if (file.size > MAX_SIZE) {
              message.error('文件大小不能超过 20MB');
              return Upload.LIST_IGNORE;
            }
            return true;
          }}
        >
          <Button type="primary" icon={<CloudUploadOutlined />}>
            上传文件
          </Button>
        </Upload>
      </div>

      {/* 表格区 */}
      <Table<DocumentItem>
        rowKey="id"
        loading={isLoading}
        columns={columns}
        dataSource={data?.items ?? []}
        pagination={false}
        locale={{
          emptyText:
            debouncedKeyword ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <>
                    <div>未找到匹配的文件</div>
                    <Button type="link" size="small" onClick={() => setKeyword('')}>
                      清空搜索
                    </Button>
                  </>
                }
              />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无文档，请上传文件"
              />
            ),
        }}
      />
      {(data?.total ?? 0) > 0 && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
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
  );
}
