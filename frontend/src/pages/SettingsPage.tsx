/** 系统设置页（07 §2）：六个 Tab，仅 admin 可访问（后端统一 403）。 */

import { Tabs } from 'antd';

import AccessTab from './settings/AccessTab';
import AuditTab from './settings/AuditTab';
import ChannelConfigTab from './settings/ChannelConfigTab';
import DataTab from './settings/DataTab';
import ModelTab from './settings/ModelTab';
import PromptTab from './settings/PromptTab';
import RulesTab from './settings/RulesTab';

export default function SettingsPage() {
  return (
    <div>
      <h1 className="page-title">系统设置</h1>
      <p className="page-sub">模型、Prompt、客服规则、账号权限、日志审计与数据管理（07_帮助文档与系统设置.md）</p>
      <div style={{ marginTop: 16 }}>
        <Tabs
          items={[
            { key: 'model', label: '模型配置', children: <ModelTab /> },
            { key: 'prompt', label: 'Prompt 配置', children: <PromptTab /> },
            { key: 'rules', label: '客服规则', children: <RulesTab /> },
            { key: 'access', label: '账号权限', children: <AccessTab /> },
            { key: 'channel', label: '渠道配置', children: <ChannelConfigTab /> },
            { key: 'audit', label: '日志审计', children: <AuditTab /> },
            { key: 'data', label: '数据管理', children: <DataTab /> },
          ]}
        />
      </div>
    </div>
  );
}
