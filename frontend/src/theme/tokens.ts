/**
 * 全局设计令牌（需求文档 01 §4）
 * 色彩 / 字体 / 间距 / 圆角 / 阴影统一在此定义，并通过 Ant Design 5 token 落地。
 */

import type { ThemeConfig } from 'antd';

export const designTokens = {
  // 色彩（01 §4.1，基于原型浅色主题）
  colorPrimary: '#3B82F6',
  colorPrimaryDark: '#2563EB',
  colorPrimaryLight: '#EFF6FF',
  colorBgLayout: '#F5F6FA',
  colorBgContainer: '#FFFFFF',
  colorBorder: '#E5E7EB',
  colorText: '#1F2937',
  colorTextSecondary: '#6B7280',
  colorTextPlaceholder: '#9CA3AF',
  colorSuccess: '#16A34A',
  colorWarning: '#F59E0B',
  colorError: '#EF4444',
  colorInfo: '#3B82F6',
  // 字体（01 §4.2）
  fontFamily:
    '-apple-system, "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif',
  fontSize: 14,
  // 圆角（01 §4.3）
  borderRadius: 10,
  borderRadiusLG: 14,
  // 阴影（01 §4.3）
  boxShadow: '0 1px 3px rgba(0,0,0,.06)',
  boxShadowHover: '0 4px 12px rgba(0,0,0,.10)',
} as const;

export const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: designTokens.colorPrimary,
    colorInfo: designTokens.colorInfo,
    colorSuccess: designTokens.colorSuccess,
    colorWarning: designTokens.colorWarning,
    colorError: designTokens.colorError,
    colorBgLayout: designTokens.colorBgLayout,
    colorBgContainer: designTokens.colorBgContainer,
    colorBorder: designTokens.colorBorder,
    colorText: designTokens.colorText,
    colorTextSecondary: designTokens.colorTextSecondary,
    colorTextPlaceholder: designTokens.colorTextPlaceholder,
    colorLink: designTokens.colorPrimaryDark,
    borderRadius: designTokens.borderRadius,
    borderRadiusLG: designTokens.borderRadiusLG,
    fontFamily: designTokens.fontFamily,
    fontSize: designTokens.fontSize,
  },
  components: {
    Layout: {
      siderBg: '#FFFFFF',
      headerBg: '#FFFFFF',
      headerHeight: 56,
      bodyBg: '#F5F6FA',
    },
    Menu: {
      itemSelectedBg: '#EFF6FF',
      itemSelectedColor: '#2563EB',
      itemHoverBg: '#F3F4F6',
      itemBorderRadius: 10,
      itemHeight: 42,
    },
    Card: {
      borderRadiusLG: 14,
    },
    Table: {
      headerBg: '#F9FAFB',
      headerColor: '#6B7280',
    },
  },
};

