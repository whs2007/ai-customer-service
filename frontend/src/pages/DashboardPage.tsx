/** 工作台（02）：4 张 KPI 卡片 + 近 7 日会话趋势 + 意图分布环形图，30s 自动刷新。 */

import {
  CheckCircleOutlined,
  MessageOutlined,
  ReloadOutlined,
  SwapOutlined,
  AimOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Button, Card, Empty, Skeleton, Space, Tag, message } from 'antd';
import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { getIntents, getStats, getTrend } from '../api/dashboard';
import { INTENT_LABELS } from '../api/sessions';

const PIE_COLORS = ['#3B82F6', '#16A34A', '#F59E0B', '#EF4444', '#8B5CF6', '#06B6D4'];

function KpiCard({
  icon,
  label,
  value,
  unit,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  unit?: string;
  onClick?: () => void;
}) {
  return (
    <Card
      hoverable={Boolean(onClick)}
      onClick={onClick}
      style={{ borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)', cursor: onClick ? 'pointer' : 'default' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: 12,
            background: '#EFF6FF',
            color: '#2563EB',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 20,
            flexShrink: 0,
          }}
        >
          {icon}
        </div>
        <div>
          <div style={{ fontSize: 13, color: '#6B7280' }}>{label}</div>
          <div style={{ fontSize: 30, fontWeight: 700, lineHeight: 1.2 }} className="num">
            {value}
            {unit && <span style={{ fontSize: 16, marginLeft: 2 }}>{unit}</span>}
          </div>
        </div>
      </div>
    </Card>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const [refreshTick, setRefreshTick] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const statsQuery = useQuery({
    queryKey: ['dashboard-stats', refreshTick],
    queryFn: getStats,
  });
  const trendQuery = useQuery({
    queryKey: ['dashboard-trend', refreshTick],
    queryFn: () => getTrend(7),
  });
  const intentsQuery = useQuery({
    queryKey: ['dashboard-intents', refreshTick],
    queryFn: () => getIntents(7),
  });

  // 自动刷新 30s（02 §6 建议 30–60s）
  useEffect(() => {
    if (!autoRefresh) return;
    const timer = setInterval(() => setRefreshTick((t) => t + 1), 30_000);
    return () => clearInterval(timer);
  }, [autoRefresh]);

  const loading = statsQuery.isLoading || trendQuery.isLoading || intentsQuery.isLoading;
  const failed = [statsQuery, trendQuery, intentsQuery].some((q) => q.isError);

  useEffect(() => {
    if (failed) {
      message.error('数据加载失败');
    }
  }, [failed]);

  const stats = statsQuery.data;
  const trendData = (trendQuery.data ?? []).map((p) => ({
    ...p,
    label: p.date.slice(5), // MM-DD
  }));
  const intents = intentsQuery.data;
  const pieData = (intents?.items ?? []).map((i) => ({
    name: INTENT_LABELS[i.intent] ?? i.intent,
    value: i.count,
  }));

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h1 className="page-title" style={{ margin: 0 }}>
          工作台
        </h1>
        <div style={{ flex: 1 }} />
        <Button
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={() => setRefreshTick((t) => t + 1)}
        >
          刷新
        </Button>
        <Tag
          color={autoRefresh ? 'blue' : 'default'}
          style={{ cursor: 'pointer' }}
          onClick={() => setAutoRefresh((v) => !v)}
        >
          自动刷新 {autoRefresh ? '开' : '关'}
        </Tag>
      </div>

      {loading ? (
        <Skeleton active paragraph={{ rows: 4 }} style={{ marginTop: 24 }} />
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginTop: 16 }}>
            <KpiCard
              icon={<MessageOutlined />}
              label="今日会话数"
              value={String(stats?.today_sessions ?? 0)}
              onClick={() => navigate('/sessions')}
            />
            <KpiCard
              icon={<CheckCircleOutlined />}
              label="AI 自动解决率"
              value={String(stats?.ai_solved_rate ?? 0)}
              unit="%"
            />
            <KpiCard
              icon={<SwapOutlined />}
              label="转人工数量"
              value={String(stats?.transfer_count ?? 0)}
              onClick={() => navigate('/tickets')}
            />
            <KpiCard
              icon={<AimOutlined />}
              label="知识库命中率"
              value={String(stats?.kb_hit_rate ?? 0)}
              unit="%"
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
            <Card
              title="会话趋势"
              extra="近 7 日"
              style={{ borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}
            >
              {trendData.length === 0 ? (
                <Empty description="暂无会话数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={trendData}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="label" />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="sessions" name="会话数" fill="#3B82F6" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </Card>

            <Card
              title="意图分布"
              extra="近 7 日"
              style={{ borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}
            >
              {pieData.length === 0 ? (
                <Empty description="暂无意图数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={60}
                      outerRadius={100}
                      paddingAngle={2}
                    >
                      {pieData.map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </Card>
          </div>
        </>
      )}
      <Space style={{ marginTop: 8, fontSize: 12, color: '#9CA3AF' }}>
        KPI 口径按 02 §7；AI 自动解决率以“当日未转人工会话/当日会话”近似（详见需求功能报告 §16）
      </Space>
    </div>
  );
}
