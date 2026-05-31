import { fireEvent } from '@testing-library/react-native';
import React from 'react';

import { FlavorFingerprint } from '../components/FlavorFingerprint';
import { SentimentControl } from '../components/SentimentControl';
import { Button } from '../ui/Button';
import { renderWithTheme } from './utils';

const SCORES = {
  umami: 0.8, spicy: 0.2, sour: 0, sweet: 0, bitter: 0,
  rich: 0.5, herbaceous: 0, smoky: 0, fermented: 0, fresh: 0.9,
};

describe('SentimentControl (hard-negative emitter)', () => {
  it('emits "disliked" when Not for me is tapped', () => {
    const onChange = jest.fn();
    const { getByText } = renderWithTheme(<SentimentControl onChange={onChange} />);
    fireEvent.press(getByText('Not for me'));
    expect(onChange).toHaveBeenCalledWith('disliked');
  });

  it('emits "liked" when Like is tapped', () => {
    const onChange = jest.fn();
    const { getByText } = renderWithTheme(<SentimentControl onChange={onChange} />);
    fireEvent.press(getByText('Like'));
    expect(onChange).toHaveBeenCalledWith('liked');
  });
});

describe('FlavorFingerprint', () => {
  it('lollipop lists the flavor dimensions', () => {
    const { getByText } = renderWithTheme(<FlavorFingerprint scores={SCORES} variant="lollipop" />);
    ['umami', 'spicy', 'rich', 'fresh'].forEach((dim) => expect(getByText(dim)).toBeTruthy());
  });

  it('spectrum renders as a labeled bar', () => {
    const { getByLabelText } = renderWithTheme(<FlavorFingerprint scores={SCORES} variant="spectrum" />);
    expect(getByLabelText('Flavor spectrum')).toBeTruthy();
  });
});

describe('Button', () => {
  it('calls onPress', () => {
    const onPress = jest.fn();
    const { getByText } = renderWithTheme(<Button title="Log it" onPress={onPress} />);
    fireEvent.press(getByText('Log it'));
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});
