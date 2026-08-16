/** 设计令牌结构冒烟测试。 */

import { describe, expect, it } from 'vitest';

import { designTokens } from './tokens';

describe('design tokens', () => {
  it('包含主色与圆角等关键令牌', () => {
    expect(designTokens.colorPrimary).toBeDefined();
    expect(designTokens.borderRadius).toBeDefined();
  });
});
