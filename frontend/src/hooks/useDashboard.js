import { useQuery } from '@tanstack/react-query';
import { getDashboardMetrics, getDashboardAnalytics } from '../api/dashboard';

export const useDashboard = () => {
  return useQuery({
    queryKey: ['dashboardMetrics'],
    queryFn: getDashboardMetrics,
    refetchInterval: 30000,
    retry: false,
    refetchOnMount: true,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
};

export const useDashboardAnalytics = () => {
  return useQuery({
    queryKey: ['dashboardAnalytics'],
    queryFn: getDashboardAnalytics,
    refetchInterval: 30000,
    retry: false,
    refetchOnMount: true,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
};