import React, { useState, useEffect } from 'react';
import {
  Box, Grid, Paper, Typography, TextField, Button, RadioGroup, FormControlLabel, Radio,
  Select, MenuItem, FormControl, InputLabel, Checkbox, FormGroup, Divider, Chip, IconButton,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Alert
} from '@mui/material';
import { Download, FileText, Shield, HardDrive, RefreshCw, Eye } from 'lucide-react';
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs';
import { LocalizationProvider, DatePicker } from '@mui/x-date-pickers';
import dayjs from 'dayjs';
import { useDashboardAnalytics } from '../hooks/useDashboard';
import { useExportData, useExportHistory } from '../hooks/useExport';
import { useProcessedArticles } from '../hooks/useArticles';

const Export = () => {
  const { data: analyticsData } = useDashboardAnalytics();
  const exportDataMutation = useExportData();
  const { data: historyData = [], isLoading: historyLoading } = useExportHistory();

  const [source, setSource] = useState('All');
  const [status, setStatus] = useState('Processed');
  const [dateRange, setDateRange] = useState([dayjs().subtract(15, 'day'), dayjs()]);
  const [dataType, setDataType] = useState('all');
  const [format, setFormat] = useState('csv');
  const [estimatedFileSize, setEstimatedFileSize] = useState('0 KB');

  const [fields, setFields] = useState({
    metadata: true,
    iocs: true,
    malwareActors: true,
    mitre: true,
    additional: false,
  });

  // Fetch processed articles to estimate file size
  const { data: processedData } = useProcessedArticles({
    page: 1,
    page_size: 1000,
    source_domain: source !== 'All' ? source : undefined,
    date_from: dateRange[0] ? dateRange[0].toISOString() : undefined,
    date_to: dateRange[1] ? dateRange[1].toISOString() : undefined,
  });

  useEffect(() => {
    if (processedData?.data) {
      const records = processedData.data;
      // Rough estimate: 1KB per record for CSV, 2KB for JSON, 3KB for XLSX
      let sizePerRecord = 1024;
      if (format === 'json') sizePerRecord = 2048;
      else if (format === 'xlsx') sizePerRecord = 3072;
      const totalBytes = records.length * sizePerRecord;
      if (totalBytes < 1024) {
        setEstimatedFileSize(`${totalBytes} B`);
      } else if (totalBytes < 1024 * 1024) {
        setEstimatedFileSize(`${(totalBytes / 1024).toFixed(1)} KB`);
      } else {
        setEstimatedFileSize(`${(totalBytes / (1024 * 1024)).toFixed(2)} MB`);
      }
    } else {
      setEstimatedFileSize('0 KB');
    }
  }, [processedData, format]);

  // Compute total IOCs from analytics
  const totalIOCs = analyticsData?.ioc_distribution
    ? Object.values(analyticsData.ioc_distribution).reduce((a, b) => a + b, 0)
    : 0;

  const kpiData = [
    { title: 'Processed Articles', value: analyticsData?.metrics?.processed || 0, sub: 'Selected for export', icon: FileText, color: '#22C55E' },
    { title: 'Total IOCs', value: totalIOCs, sub: 'Across selected articles', icon: Shield, color: '#3B82F6' },
    { title: 'Estimated file size', value: estimatedFileSize, sub: format.toUpperCase() + ' format', icon: HardDrive, color: '#F59E0B' },
  ];

  const handleExport = () => {
    const params = {
      source: source !== 'All' ? source : undefined,
      status,
      date_from: dateRange[0].toISOString(),
      date_to: dateRange[1].toISOString(),
      data_type: dataType,
      format
    };
    exportDataMutation.mutate(params);
  };

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5" fontWeight="bold">Export</Typography>
        <Typography variant="body2" color="text.secondary">Export processed threat intelligence in your preferred format.</Typography>
      </Box>

      <Grid container spacing={3} sx={{ mb: 3 }}>
        {kpiData.map((kpi, idx) => (
          <Grid item xs={12} sm={6} md={4} lg={4} key={idx} sx={{ display: 'flex' }}>
            <Paper sx={{ p: 2, width: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <Box sx={{ p: 0.5, borderRadius: 1, color: kpi.color }}>
                  <kpi.icon size={18} />
                </Box>
                <Typography variant="body2" color="text.secondary">{kpi.title}</Typography>
              </Box>
              <Typography variant="h5" fontWeight="bold">{typeof kpi.value === 'string' ? kpi.value : kpi.value.toLocaleString()}</Typography>
              <Typography variant="caption" color="text.secondary">{kpi.sub}</Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>

      <Grid container spacing={3}>
        {/* Data Selection */}
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" fontWeight="bold" sx={{ mb: 3 }}>1. Select Data</Typography>

            <FormControl fullWidth size="small" sx={{ mb: 2 }}>
              <InputLabel>Select Source (optional)</InputLabel>
              <Select value={source} onChange={(e) => setSource(e.target.value)} label="Select Source (optional)">
                <MenuItem value="All">All Sources</MenuItem>
              </Select>
            </FormControl>

            <FormControl fullWidth size="small" sx={{ mb: 2 }}>
              <InputLabel>Select Status</InputLabel>
              <Select value={status} onChange={(e) => setStatus(e.target.value)} label="Select Status">
                <MenuItem value="Processed">Processed</MenuItem>
              </Select>
            </FormControl>

            <LocalizationProvider dateAdapter={AdapterDayjs}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mb: 3 }}>
                <DatePicker label="From" value={dateRange[0]} onChange={(val) => setDateRange([val, dateRange[1]])} slotProps={{ textField: { size: 'small', fullWidth: true } }} />
                <DatePicker label="To" value={dateRange[1]} onChange={(val) => setDateRange([dateRange[0], val])} slotProps={{ textField: { size: 'small', fullWidth: true } }} />
              </Box>
            </LocalizationProvider>

            <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>Data Type</Typography>
            <RadioGroup value={dataType} onChange={(e) => setDataType(e.target.value)}>
              <FormControlLabel value="all" control={<Radio size="small" />} label="All Data (Articles + IOCs + Metadata)" />
              <FormControlLabel value="iocs" control={<Radio size="small" />} label="IOCs Only" />
              <FormControlLabel value="articles" control={<Radio size="small" />} label="Articles Only" />
              <FormControlLabel value="summary" control={<Radio size="small" />} label="Summary & Metadata Only" />
            </RadioGroup>
          </Paper>
        </Grid>

        {/* Field Selection */}
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" fontWeight="bold" sx={{ mb: 3 }}>2. Select Fields</Typography>

            <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>Article Metadata</Typography>
            <FormGroup sx={{ mb: 2, pl: 1 }}>
              <FormControlLabel control={<Checkbox checked={fields.metadata} onChange={() => setFields({...fields, metadata: !fields.metadata})} size="small" />} label={<Typography variant="caption">Title, Source, Published At, Author, etc.</Typography>} />
            </FormGroup>

            <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>IOCs</Typography>
            <FormGroup sx={{ mb: 2, pl: 1 }}>
              <FormControlLabel control={<Checkbox checked={fields.iocs} onChange={() => setFields({...fields, iocs: !fields.iocs})} size="small" />} label={<Typography variant="caption">Domains, URLs, IPs, Hashes, Emails</Typography>} />
            </FormGroup>

            <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>Malware & Threat Actors</Typography>
            <FormGroup sx={{ mb: 2, pl: 1 }}>
              <FormControlLabel control={<Checkbox checked={fields.malwareActors} onChange={() => setFields({...fields, malwareActors: !fields.malwareActors})} size="small" />} label={<Typography variant="caption">Malware Families, Threat Actors</Typography>} />
            </FormGroup>

            <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>MITRE ATT&CK</Typography>
            <FormGroup sx={{ mb: 2, pl: 1 }}>
              <FormControlLabel control={<Checkbox checked={fields.mitre} onChange={() => setFields({...fields, mitre: !fields.mitre})} size="small" />} label={<Typography variant="caption">Techniques, Tactics</Typography>} />
            </FormGroup>

            <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>Additional Content</Typography>
            <FormGroup sx={{ pl: 1 }}>
              <FormControlLabel control={<Checkbox checked={fields.additional} onChange={() => setFields({...fields, additional: !fields.additional})} size="small" />} label={<Typography variant="caption">Tags, Confidence, Notes</Typography>} />
            </FormGroup>
          </Paper>
        </Grid>

        {/* Format & Export */}
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" fontWeight="bold" sx={{ mb: 3 }}>3. Choose Format</Typography>

            <Box sx={{ mb: 3 }}>
              <FormControlLabel
                value="csv"
                control={<Radio checked={format === 'csv'} onChange={() => setFormat('csv')} />}
                label={<Box><Typography variant="body2" fontWeight="bold">CSV (Recommended)</Typography><Typography variant="caption" color="text.secondary">Best for spreadsheets and analysis</Typography></Box>}
                sx={{ mb: 1, display: 'block' }}
              />
              <FormControlLabel
                value="json"
                control={<Radio checked={format === 'json'} onChange={() => setFormat('json')} />}
                label={<Box><Typography variant="body2" fontWeight="bold">JSON</Typography><Typography variant="caption" color="text.secondary">Best for systems and automation</Typography></Box>}
                sx={{ mb: 1, display: 'block' }}
              />
              <FormControlLabel
                value="xlsx"
                control={<Radio checked={format === 'xlsx'} onChange={() => setFormat('xlsx')} />}
                label={<Box><Typography variant="body2" fontWeight="bold">Excel (XLSX)</Typography><Typography variant="caption" color="text.secondary">Best for reports and sharing</Typography></Box>}
                sx={{ display: 'block' }}
              />
            </Box>

            <Alert severity="info" sx={{ mb: 3, alignItems: 'center' }}>
              <Typography variant="caption" display="block">You will receive an email with download link.</Typography>
              <Typography variant="caption" display="block">Exports are available for 7 days.</Typography>
            </Alert>

            <Button
              variant="contained"
              fullWidth
              size="large"
              startIcon={<Download size={20} />}
              disabled={exportDataMutation.isPending}
              onClick={handleExport}
              sx={{ fontWeight: 600 }}
            >
              {exportDataMutation.isPending ? 'Generating...' : 'Export Data'}
            </Button>
          </Paper>
        </Grid>
      </Grid>

      {/* Export History */}
      <Paper sx={{ p: 3, mt: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6" fontWeight="bold">Recent Exports</Typography>
        </Box>

        <TableContainer>
          <Table sx={{ minWidth: 650 }}>
            <TableHead sx={{ bgcolor: '#F1F5F9' }}>
              <TableRow>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Export ID</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Date & Time</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Data Type</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Format</TableCell>
                <TableCell align="right" sx={{ fontWeight: 600, color: 'text.secondary' }}>Records</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>File Size</TableCell>
                <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Status</TableCell>
                <TableCell align="center" sx={{ fontWeight: 600, color: 'text.secondary' }}>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {historyLoading ? (
                <TableRow><TableCell colSpan={8} align="center" sx={{ py: 3 }}>Loading history...</TableCell></TableRow>
              ) : historyData.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} align="center" sx={{ py: 4 }}>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>No export history found.</Typography>
                    <Typography variant="caption" color="text.disabled">Export history requires a backend `GET /api/v1/export/history` endpoint.</Typography>
                  </TableCell>
                </TableRow>
              ) : (
                historyData.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell component="th" scope="row">{row.id}</TableCell>
                    <TableCell>{new Date(row.created_at).toLocaleString()}</TableCell>
                    <TableCell>{row.data_type}</TableCell>
                    <TableCell>{row.format}</TableCell>
                    <TableCell align="right">{row.records}</TableCell>
                    <TableCell>{row.size}</TableCell>
                    <TableCell>
                      <Chip
                        label={row.status}
                        size="small"
                        color={row.status === 'Completed' ? 'success' : 'default'}
                        sx={{ fontWeight: 600 }}
                      />
                    </TableCell>
                    <TableCell align="center">
                      <IconButton size="small"><Eye size={16} /></IconButton>
                      <IconButton size="small"><Download size={16} /></IconButton>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Box>
  );
};

export default Export;