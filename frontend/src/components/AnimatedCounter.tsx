import React, { useEffect, useRef } from "react";
import { Text, TextProps, Animated, Easing } from "react-native";
import { formatINR } from "@/src/utils/format";

type Props = TextProps & {
  value: number;
  formatter?: (n: number) => string;
  duration?: number;
  decimals?: number;
};

// Smooth counter animation for amounts
export function AnimatedCounter({
  value,
  formatter,
  duration = 900,
  decimals = 0,
  style,
  ...rest
}: Props) {
  const animated = useRef(new Animated.Value(0)).current;
  const [display, setDisplay] = React.useState(0);

  useEffect(() => {
    const id = animated.addListener(({ value: v }) => setDisplay(v));
    Animated.timing(animated, {
      toValue: value,
      duration,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
    return () => animated.removeListener(id);
  }, [value, duration, animated]);

  const text = formatter ? formatter(display) : formatINR(Number(display.toFixed(decimals)));
  return <Text style={style} {...rest}>{text}</Text>;
}
