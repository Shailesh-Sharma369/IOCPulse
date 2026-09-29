import React, { useState, useMemo } from 'react';
import {
  Box, Grid, Paper, Typography, TextField, InputAdornment,
  Select, MenuItem, FormControl, Chip, IconButton, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow,
  TablePagination, Button, Checkbox, Alert
} from '@mui/material';
import { Search, RefreshCw, FileText, Shield, Bug, User, Target, Eye, Download } from 'lucide-react';
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs';
import { LocalizationProvider, DatePicker } from '@mui/x-date-pickers';
import dayjs from 'dayjs';
import { useDashboard } from '../hooks/useDashboard';
import { useProcessedArticles } from '../hooks/useArticles';
import ProcessedDetailPanel from '../components/ProcessedArticles/ProcessedDetailPanel';

const ProcessedArticles = () => {
  const { data: dashboardData } = useDashboard();

  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [searchQuery, setSearchQuery] = useState('');
  const [sourceFilter, setSourceFilter] = useState('All');
  const [statusFilter, setStatusFilter] = useState('All');
  const [iocTypeFilter, setIocTypeFilter] = useState('All');
  const [dateRange, setDateRange] = useState([null, null]);
  const [selectedArticleId, setSelectedArticleId] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);

  const apiParams = {
    page: page + 1,
    page_size: rowsPerPage,
    source_domain: sourceFilter !== 'All' ? sourceFilter : undefined,
    verification_status: statusFilter !== 'All' ? statusFilter.toLowerCase() : undefined,
    date_from: dateRange[0] ? dateRange[0].toISOString() : undefined,
    date_to: dateRange[1] ? dateRange[1].toISOString() : undefined,
    sort_by: 'p.processing_timestamp',
    sort_dir: 'DESC'
  };

  const { data: processedData, isLoading, error, refetch } = useProcessedArticles(apiParams);
  const articles = processedData?.data || [];
  const pagination = processedData?.pagination || { total: 0, page: 1, page_size: 10 };

  // Compute aggregated KPI values from the articles list
  const aggregatedKpi = useMemo(() => {
    let totalIOCs = 0;
    const malwareSet = new Set();
    const actorSet = new Set();
    const mitreSet = new Set();

    articles.forEach(article => {
      if (article.iocs && typeof article.iocs === 'object') {
        Object.values(article.iocs).forEach(arr => {
          if (Array.isArray(arr)) totalIOCs += arr.length;
        });
      } else if (typeof article.iocs === 'string') {
        try {
          const parsed = JSON.parse(article.iocs);
          Object.values(parsed).forEach(arr => {
            if (Array.isArray(arr)) totalIOCs += arr.length;
          });
        } catch (e) {}
      }

      if (article.threat_metadata) {
        const meta = typeof article.threat_metadata === 'string' ? JSON.parse(article.threat_metadata) : article.threat_metadata;
        (meta.malware_name || []).forEach(m => malwareSet.add(m));
        (meta.threat_actor || []).forEach(a => actorSet.add(a));
        (meta.mitre_techniques || []).forEach(t => mitreSet.add(t));
      }
    });

    return {
      totalIOCs,
      malwareCount: malwareSet.size,
      actorCount: actorSet.size,
      mitreCount: mitreSet.size,
    };
  }, [articles]);

  const kpiData = [
    { title: 'Processed Articles', value: dashboardData?.processed || 0, icon: FileText, color: '#22C55E', sub: `${((dashboardData?.processed || 0) / (dashboardData?.total_raw || 1) * 100).toFixed(1)}% of total` },
    { title: 'IOCs Extracted', value: aggregatedKpi.totalIOCs, icon: Shield, color: '#3B82F6', sub: 'Total IOCs' },
    { title: 'Malware Families', value: aggregatedKpi.malwareCount, icon: Bug, color: '#8B5CF6', sub: 'Unique malware' },
    { title: 'Threat Actors', value: aggregatedKpi.actorCount, icon: User, color: '#F59E0B', sub: 'Unique actors' },
    { title: 'MITRE Techniques', value: aggregatedKpi.mitreCount, icon: Target, color: '#EF4444', sub: 'Unique techniques' },
  ];

  const getStatusChip = (status) => {
    const colors = {
      'verified': { bg: '#22C55E15', text: '#22C55E' },
      'partial': { bg: '#F59E0B15', text: '#F59E0B' },
      'low': { bg: '#EF444415', text: '#EF4444' },
    };
    const style = colors[status] || { bg: '#64748B15', text: '#64748B' };
    return <Chip label={status || 'Unknown'} size="small" sx={{ bgcolor: style.bg, color: style.text, fontWeight: 600, borderRadius: 1 }} />;
  };

  const handleSelectAll = (event) => {
    if (event.target.checked) {
      const newSelected = articles.map((n) => n.id);
      setSelectedIds(newSelected);
      return;
    }
    setSelectedIds([]);
  };

  const handleSelectOne = (id) => {
    const selectedIndex = selectedIds.indexOf(id);
    let newSelected = [];
    if (selectedIndex === -1) {
      newSelected = newSelected.concat(selectedIds, id);
    } else if (selectedIndex === 0) {
      newSelected = newSelected.concat(selectedIds.slice(1));
    } else if (selectedIndex === selectedIds.length - 1) {
      newSelected = newSelected.concat(selectedIds.slice(0, -1));
    } else if (selectedIndex > 0) {
      newSelected = newSelected.concat(
        selectedIds.slice(0, selectedIndex),
        selectedIds.slice(selectedIndex + 1),
      );
    }
    setSelectedIds(newSelected);
  };

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5" fontWeight="bold">Processed Articles</Typography>
        <Typography variant="body2" color="text.secondary">Browse and analyze articles processed by Module 2 (AI Processing).</Typography>
      </Box>

      <Grid container spacing={3} sx={{ mb: 3 }}>
        {kpiData.map((kpi, idx) => (
          <Grid item xs={12} sm={6} md={4} lg={2.4} key={idx} sx={{ display: 'flex' }}>
            <Paper sx={{ p: 2, width: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <Box sx={{ p: 0.5, borderRadius: 1, color: kpi.color }}>
                  <kpi.icon size={18} />
                </Box>
                <Typography variant="body2" color="text.secondary">{kpi.title}</Typography>
              </Box>
              <Typography variant="h5" fontWeight="bold">{kpi.value.toLocaleString()}</Typography>
              <Typography variant="caption" color="text.secondary">{kpi.sub}</Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>

      <Paper sx={{ p: 2, mb: 3, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 2 }}>
        <TextField
          placeholder="Search title, summary, IOC, malware..."
          size="small"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          sx={{ flexGrow: 1, minWidth: 200 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><Search size={18} /></InputAdornment> }}
        />

        <FormControl size="small" sx={{ minWidth: 130 }}>
          <Select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
            <MenuItem value="All">Source</MenuItem>
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 120 }}>
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <MenuItem value="All">All Status</MenuItem>
            <MenuItem value="verified">Verified</MenuItem>
            <MenuItem value="partial">Partial</MenuItem>
            <MenuItem value="low">Low</MenuItem>
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 120 }}>
          <Select value={iocTypeFilter} onChange={(e) => setIocTypeFilter(e.target.value)}>
            <MenuItem value="All">IOC Type</MenuItem>
            <MenuItem value="domains">Domains</MenuItem>
            <MenuItem value="ips">IPs</MenuItem>
            <MenuItem value="urls">URLs</MenuItem>
            <MenuItem value="hashes">Hashes</MenuItem>
            <MenuItem value="emails">Emails</MenuItem>
          </Select>
        </FormControl>

        <LocalizationProvider dateAdapter={AdapterDayjs}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <DatePicker label="From" value={dateRange[0]} onChange={(val) => setDateRange([val, dateRange[1]])} slotProps={{ textField: { size: 'small', sx: { width: 130 } } }} />
            <DatePicker label="To" value={dateRange[1]} onChange={(val) => setDateRange([dateRange[0], val])} slotProps={{ textField: { size: 'small', sx: { width: 130 } } }} />
          </Box>
        </LocalizationProvider>

        <Button variant="text" startIcon={<RefreshCw size={16} />} onClick={() => refetch()} size="small">
          Refresh
        </Button>

        <Button variant="contained" startIcon={<Download size={16} />} size="small" disabled={selectedIds.length === 0}>
          Export Selected
        </Button>
      </Paper>

      <Paper>
        <TableContainer>
          <Table sx={{ minWidth: 750 }}>
            <TableHead sx={{ bgcolor: '#F1F5F9' }}>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    indeterminate={selectedIds.length > 0 && selectedIds.length < articles.length}
                    checked={articles.length > 0 && selectedIds.length === articles.length}
                    onChange={handleSelectAll}
                  />
                </TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Title</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Source</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Processed At</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>IOCs</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Malware / Actors</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>MITRE ATT&CK</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Status</TableCell>
                <TableCell align="center" sx={{ fontWeight: 600, color: 'text.secondary' }}>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={9} align="center" sx={{ py: 3 }}>Loading intelligence...</TableCell></TableRow>
              ) : error ? (
                <TableRow><TableCell colSpan={9} align="center" sx={{ py: 3, color: 'status.failed' }}>
                  <Alert severity="error" sx={{ justifyContent: 'center' }}>
                    Failed to connect to backend. Please check CORS and Database connection. Console logs show: {error.message}
                  </Alert>
                </TableCell></TableRow>
              ) : articles.length === 0 ? (
                <TableRow><TableCell colSpan={9} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                  No processed articles found.
                </TableCell></TableRow>
              ) : (
                articles.map((article) => {
                  let iocCount = 0;
                  if (article.iocs && typeof article.iocs === 'object') {
                    Object.values(article.iocs).forEach(arr => iocCount += arr.length);
                  } else if (typeof article.iocs === 'string') {
                    try { const parsed = JSON.parse(article.iocs); Object.values(parsed).forEach(arr => iocCount += arr.length); } catch (e) {}
                  }

                  let malwareActors = [];
                  if (article.threat_metadata) {
                    const meta = typeof article.threat_metadata === 'string' ? JSON.parse(article.threat_metadata) : article.threat_metadata;
                    malwareActors = [...(meta.malware_name || []), ...(meta.threat_actor || [])];
                  }

                  const mitreCount = article.mitre_techniques?.length || 0;
                  const isItemSelected = selectedIds.indexOf(article.id) !== -1;

                  return (
                    <TableRow key={article.id} hover selected={isItemSelected}>
                      <TableCell padding="checkbox">
                        <Checkbox checked={isItemSelected} onClick={() => handleSelectOne(article.id)} />
                      </TableCell>
                      <TableCell component="th" scope="row" sx={{ fontWeight: 500 }}>{article.title || 'Untitled'}</TableCell>
                      <TableCell>{article.source_domain}</TableCell>
                      <TableCell>{article.processing_timestamp ? new Date(article.processing_timestamp).toLocaleString() : '-'}</TableCell>
                      <TableCell>{iocCount}</TableCell>
                      <TableCell>
                        {malwareActors.length > 0 ? (
                          malwareActors.slice(0, 2).map((item, idx) => (
                            <Chip key={idx} label={item} size="small" variant="outlined" sx={{ mr: 0.5, mb: 0.5, fontSize: '0.7rem', height: 20 }} />
                          ))
                        ) : '-'}
                      </TableCell>
                      <TableCell>{mitreCount > 0 ? mitreCount : '-'}</TableCell>
                      <TableCell>{getStatusChip(article.verification_status)}</TableCell>
                      <TableCell align="center">
                        <IconButton size="small" onClick={() => setSelectedArticleId(article.id)}>
                          <Eye size={16} />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </TableContainer>

        <TablePagination
          rowsPerPageOptions={[10, 25, 50]}
          component="div"
          count={pagination.total || 0}
          rowsPerPage={rowsPerPage}
          page={page}
          onPageChange={(e, newPage) => setPage(newPage)}
          onRowsPerPageChange={(e) => {
            setRowsPerPage(parseInt(e.target.value, 10));
            setPage(0);
          }}
        />
      </Paper>

      <ProcessedDetailPanel
        open={!!selectedArticleId}
        onClose={() => setSelectedArticleId(null)}
        articleId={selectedArticleId}
      />
    </Box>
  );
};

export default ProcessedArticles;