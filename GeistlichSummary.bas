Attribute VB_Name = "GeistlichSummary"
' ============================================================
' Geistlich Monthly Sales Summary Generator
' ------------------------------------------------------------
' HOW TO INSTALL (one-time):
'   1. Open any Excel workbook and save it as .xlsm
'      (File > Save As > Excel Macro-Enabled Workbook)
'   2. Press Alt + F11 to open the VBA editor
'   3. In the menu: File > Import File...
'   4. Select this file (GeistlichSummary.bas)
'   5. Close the VBA editor (Alt + F11 again)
'   6. Optional: Insert > Shape, draw a button, right-click >
'      Assign Macro > select "GenerateSummary"
'
' HOW TO USE EACH MONTH:
'   Run the "GenerateSummary" macro (or click your button).
'   Four file pickers will appear — select each file when prompted.
'   The finished summary is saved in the same folder as the macro workbook.
' ============================================================

Option Explicit

Public Sub GenerateSummary()

    Dim cy_prev_path As String, cy_curr_path As String
    Dim pv_prev_path As String, pv_curr_path As String

    ' --- Pick the 4 input files ---
    cy_prev_path = PickFile("Select CY PREVIOUS Year YTD file (e.g. CY25_YTD.xlsx)")
    If cy_prev_path = "" Then Exit Sub

    cy_curr_path = PickFile("Select CY CURRENT Year YTD file (e.g. CY26_YTD.xlsx)")
    If cy_curr_path = "" Then Exit Sub

    pv_prev_path = PickFile("Select PV PREVIOUS Year YTD file (e.g. PV25_YTD.xlsx)")
    If pv_prev_path = "" Then Exit Sub

    pv_curr_path = PickFile("Select PV CURRENT Year YTD file (e.g. PV26_YTD.xlsx)")
    If pv_curr_path = "" Then Exit Sub

    ' --- Infer years from filenames ---
    Dim year_prev As String, year_curr As String
    year_prev = InferYear(cy_prev_path)
    year_curr = InferYear(cy_curr_path)

    If year_prev = "" Or year_curr = "" Then
        MsgBox "Could not determine year from filename. " & _
               "Files must contain a pattern like CY25 or PV26.", vbExclamation
        Exit Sub
    End If

    Application.ScreenUpdating = False
    Application.DisplayAlerts = False

    ' --- Load data from each file ---
    Dim cy_prev As Object, cy_curr As Object
    Dim pv_prev As Object, pv_curr As Object
    Set cy_prev = LoadCY(cy_prev_path)
    Set cy_curr = LoadCY(cy_curr_path)
    Set pv_prev = LoadPV(pv_prev_path)
    Set pv_curr = LoadPV(pv_curr_path)

    ' --- Union of all customers ---
    Dim allCustomers As Collection
    Set allCustomers = UnionCustomers(cy_prev, cy_curr, pv_prev, pv_curr)

    ' --- Sort customers alphabetically ---
    Dim sortedCustomers() As String
    sortedCustomers = SortCollection(allCustomers)

    ' --- Build output workbook ---
    Dim wbOut As Workbook
    Set wbOut = Workbooks.Add
    Dim ws As Worksheet
    Set ws = wbOut.Sheets(1)
    ws.Name = "Sheet1"

    ' Write header
    Dim headers(1 To 8) As String
    headers(1) = "Customer"
    headers(2) = "CY20" & year_prev & " YTD"
    headers(3) = "CY20" & year_prev & " PV"
    headers(4) = "CY20" & year_prev & " Total"
    headers(5) = "CY20" & year_curr & " YTD"
    headers(6) = "CY20" & year_curr & " PV"
    headers(7) = "CY20" & year_curr & " Total"
    headers(8) = "% Change"

    Dim c As Integer
    For c = 1 To 8
        With ws.Cells(1, c)
            .Value = headers(c)
            .Font.Name = "Book Antiqua"
            .Font.Size = 11
            .Font.Bold = True
            .HorizontalAlignment = xlCenter
            .Borders(xlEdgeLeft).LineStyle = xlContinuous
            .Borders(xlEdgeRight).LineStyle = xlContinuous
            .Borders(xlEdgeTop).LineStyle = xlContinuous
            .Borders(xlEdgeBottom).LineStyle = xlContinuous
            If c > 1 Then
                .NumberFormat = """$""#,##0.00_);[Red](""$""#,##0.00)"
            End If
        End With
    Next c
    ws.Row(1).RowHeight = 15

    ' Write data rows
    Dim r As Long
    r = 2
    Dim sum_prev As Double, sum_curr As Double
    sum_prev = 0
    sum_curr = 0

    Dim i As Integer
    For i = 0 To UBound(sortedCustomers)
        Dim cust As String
        cust = sortedCustomers(i)

        Dim ytd_p As Double, pv_p As Double, total_p As Double
        Dim ytd_c As Double, pv_c As Double, total_c As Double
        Dim pct As Double

        ytd_p = GetValue(cy_prev, cust)
        pv_p = GetValue(pv_prev, cust)
        total_p = ytd_p + pv_p

        ytd_c = GetValue(cy_curr, cust)
        pv_c = GetValue(pv_curr, cust)
        total_c = ytd_c + pv_c

        pct = CalcPctChange(total_p, total_c)

        sum_prev = sum_prev + total_p
        sum_curr = sum_curr + total_c

        WriteDataRow ws, r, cust, ytd_p, pv_p, total_p, ytd_c, pv_c, total_c, pct
        r = r + 1
    Next i

    ' Write Total row
    Dim total_pct As Double
    total_pct = CalcPctChange(sum_prev, sum_curr)
    WriteTotalRow ws, r, sum_prev, sum_curr, total_pct

    ' Column widths
    ws.Columns("A").ColumnWidth = 28
    ws.Columns("B").ColumnWidth = 18.57
    ws.Columns("C").ColumnWidth = 16.71
    ws.Columns("D").ColumnWidth = 19
    ws.Columns("E").ColumnWidth = 18.57
    ws.Columns("F").ColumnWidth = 16.71
    ws.Columns("G").ColumnWidth = 19
    ws.Columns("H").ColumnWidth = 15.57

    ws.Rows("1:1").Select
    ActiveWindow.FreezePanes = True
    ws.Range("A1").Select

    ' Save output
    Dim outputFolder As String
    outputFolder = ThisWorkbook.Path & "\"

    Dim today As String
    today = Format(Now(), "M.D.YYYY")

    Dim outputPath As String
    outputPath = outputFolder & "Geistlich_CY" & year_prev & "CY" & year_curr & _
                 "_Customer_Sales_" & today & ".xlsx"

    wbOut.SaveAs Filename:=outputPath, FileFormat:=xlOpenXMLWorkbook
    wbOut.Close

    Application.ScreenUpdating = True
    Application.DisplayAlerts = True

    MsgBox "Done! Saved to:" & vbNewLine & outputPath, vbInformation

End Sub

' ============================================================
' Helper: Show file picker dialog
' ============================================================
Private Function PickFile(prompt As String) As String
    Dim f As Variant
    f = Application.GetOpenFilename( _
        FileFilter:="Excel Files (*.xlsx;*.xlsm;*.xls),*.xlsx;*.xlsm;*.xls", _
        Title:=prompt)
    If f = False Then
        PickFile = ""
    Else
        PickFile = CStr(f)
    End If
End Function

' ============================================================
' Helper: Extract 2-digit year from filename (e.g. CY26 -> "26")
' ============================================================
Private Function InferYear(filePath As String) As String
    Dim fileName As String
    fileName = UCase(Mid(filePath, InStrRev(filePath, "\") + 1))
    Dim pos As Integer
    pos = InStr(fileName, "_YTD")
    If pos >= 3 Then
        InferYear = Mid(fileName, pos - 2, 2)
    Else
        InferYear = ""
    End If
End Function

' ============================================================
' Helper: Load CY file into a Dictionary (excludes Prime Vendor + Total/None)
' ============================================================
Private Function LoadCY(filePath As String) As Object
    Dim dict As Object
    Set dict = CreateObject("Scripting.Dictionary")

    Dim wb As Workbook
    Set wb = Workbooks.Open(Filename:=filePath, ReadOnly:=True, UpdateLinks:=False)
    Dim ws As Worksheet
    Set ws = wb.Sheets(1)

    Dim lastRow As Long
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row

    ' Find column indices from header
    Dim custCol As Integer, costCol As Integer, classCol As Integer
    custCol = 0: costCol = 0: classCol = 0
    Dim col As Integer
    For col = 1 To ws.Cells(1, ws.Columns.Count).End(xlToLeft).Column
        Select Case UCase(Trim(ws.Cells(1, col).Value))
            Case "CUSTOMER": custCol = col
            Case "TOTAL COST": costCol = col
            Case "CLASS": classCol = col
        End Select
    Next col

    Dim r As Long
    For r = 2 To lastRow
        Dim cust As String
        Dim cls As String
        Dim cost As Double
        cust = Trim(CStr(ws.Cells(r, custCol).Value))
        If classCol > 0 Then cls = Trim(UCase(CStr(ws.Cells(r, classCol).Value)))

        If cust = "" Or cust = "Total" Or cust = "- None -" Then GoTo NextRow
        If cls = "PRIME VENDOR" Then GoTo NextRow
        If Not IsNumeric(ws.Cells(r, costCol).Value) Then GoTo NextRow

        cost = CDbl(ws.Cells(r, costCol).Value)
        dict(cust) = cost
NextRow:
    Next r

    wb.Close False
    Set LoadCY = dict
End Function

' ============================================================
' Helper: Load PV file into a Dictionary (excludes Total/None)
' ============================================================
Private Function LoadPV(filePath As String) As Object
    Dim dict As Object
    Set dict = CreateObject("Scripting.Dictionary")

    Dim wb As Workbook
    Set wb = Workbooks.Open(Filename:=filePath, ReadOnly:=True, UpdateLinks:=False)
    Dim ws As Worksheet
    Set ws = wb.Sheets(1)

    Dim lastRow As Long
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row

    Dim custCol As Integer, costCol As Integer
    custCol = 0: costCol = 0
    Dim col As Integer
    For col = 1 To ws.Cells(1, ws.Columns.Count).End(xlToLeft).Column
        Select Case UCase(Trim(ws.Cells(1, col).Value))
            Case "CUSTOMER": custCol = col
            Case "TOTAL COST": costCol = col
        End Select
    Next col

    Dim r As Long
    For r = 2 To lastRow
        Dim cust As String
        cust = Trim(CStr(ws.Cells(r, custCol).Value))
        If cust = "" Or cust = "Total" Or cust = "- None -" Then GoTo NextRow
        If Not IsNumeric(ws.Cells(r, costCol).Value) Then GoTo NextRow
        dict(cust) = CDbl(ws.Cells(r, costCol).Value)
NextRow:
    Next r

    wb.Close False
    Set LoadPV = dict
End Function

' ============================================================
' Helper: Union of all customer keys from 4 dictionaries
' ============================================================
Private Function UnionCustomers(d1 As Object, d2 As Object, _
                                 d3 As Object, d4 As Object) As Collection
    Dim seen As Object
    Set seen = CreateObject("Scripting.Dictionary")
    Dim result As New Collection

    Dim k As Variant
    For Each k In d1.Keys: If Not seen.Exists(k) Then seen(k) = 1: result.Add k: End If: Next
    For Each k In d2.Keys: If Not seen.Exists(k) Then seen(k) = 1: result.Add k: End If: Next
    For Each k In d3.Keys: If Not seen.Exists(k) Then seen(k) = 1: result.Add k: End If: Next
    For Each k In d4.Keys: If Not seen.Exists(k) Then seen(k) = 1: result.Add k: End If: Next

    Set UnionCustomers = result
End Function

' ============================================================
' Helper: Sort a Collection of strings alphabetically
' ============================================================
Private Function SortCollection(col As Collection) As String()
    Dim n As Long
    n = col.Count
    Dim arr() As String
    ReDim arr(0 To n - 1)
    Dim i As Long
    For i = 0 To n - 1
        arr(i) = col(i + 1)
    Next i
    ' Bubble sort (list is small enough)
    Dim j As Long, tmp As String
    For i = 0 To n - 2
        For j = 0 To n - 2 - i
            If arr(j) > arr(j + 1) Then
                tmp = arr(j): arr(j) = arr(j + 1): arr(j + 1) = tmp
            End If
        Next j
    Next i
    SortCollection = arr
End Function

' ============================================================
' Helper: Safe dictionary lookup (returns 0 if key not found)
' ============================================================
Private Function GetValue(dict As Object, key As String) As Double
    If dict.Exists(key) Then
        GetValue = CDbl(dict(key))
    Else
        GetValue = 0
    End If
End Function

' ============================================================
' Helper: % change with new/lost customer handling
' ============================================================
Private Function CalcPctChange(prev As Double, curr As Double) As Double
    If prev = 0 And curr > 0 Then
        CalcPctChange = 1
    ElseIf curr = 0 And prev > 0 Then
        CalcPctChange = -1
    ElseIf prev = 0 And curr = 0 Then
        CalcPctChange = 0
    Else
        CalcPctChange = (curr - prev) / prev
    End If
End Function

' ============================================================
' Helper: Write a formatted data row
' ============================================================
Private Sub WriteDataRow(ws As Worksheet, r As Long, _
    cust As String, ytd_p As Double, pv_p As Double, total_p As Double, _
    ytd_c As Double, pv_c As Double, total_c As Double, pct As Double)

    Const CURR_FMT = """$""#,##0.00_);[Red](""$""#,##0.00)"
    Const PCT_FMT = "0.00%"
    Const FONT_NAME = "Book Antiqua"
    Const FONT_SIZE = 11

    Dim vals(1 To 8) As Variant
    vals(1) = cust: vals(2) = ytd_p: vals(3) = pv_p: vals(4) = total_p
    vals(5) = ytd_c: vals(6) = pv_c: vals(7) = total_c: vals(8) = pct

    Dim c As Integer
    For c = 1 To 8
        With ws.Cells(r, c)
            .Value = vals(c)
            .Font.Name = FONT_NAME
            .Font.Size = FONT_SIZE
            .HorizontalAlignment = xlCenter
            ' Bold: Customer, Total cols (4,7), % Change (8)
            .Font.Bold = (c = 1 Or c = 4 Or c = 7 Or c = 8)
            ' Number formats
            If c >= 2 And c <= 7 Then .NumberFormat = CURR_FMT
            If c = 8 Then .NumberFormat = PCT_FMT
            ' Borders (col B has no left border, matching original)
            If c <> 2 Then .Borders(xlEdgeLeft).LineStyle = xlContinuous
            .Borders(xlEdgeRight).LineStyle = xlContinuous
            .Borders(xlEdgeTop).LineStyle = xlContinuous
            .Borders(xlEdgeBottom).LineStyle = xlContinuous
        End With
    Next c
End Sub

' ============================================================
' Helper: Write the Total summary row
' ============================================================
Private Sub WriteTotalRow(ws As Worksheet, r As Long, _
    sum_prev As Double, sum_curr As Double, pct As Double)

    Const CURR_FMT = """$""#,##0.00_);[Red](""$""#,##0.00)"
    Const PCT_FMT = "0.00%"
    Const FONT_NAME = "Book Antiqua"
    Const FONT_SIZE = 11

    ' Only cols A, D, G, H have values and borders in the original
    Dim borderedCols(1 To 4) As Integer
    borderedCols(1) = 1: borderedCols(2) = 4: borderedCols(3) = 7: borderedCols(4) = 8

    Dim vals(1 To 8) As Variant
    vals(1) = "Total": vals(4) = sum_prev: vals(7) = sum_curr: vals(8) = pct

    Dim c As Integer
    For c = 1 To 8
        With ws.Cells(r, c)
            .Value = vals(c)
            .Font.Name = FONT_NAME
            .Font.Size = FONT_SIZE
            .HorizontalAlignment = xlCenter
            If c = 4 Or c = 7 Then .NumberFormat = CURR_FMT
            If c = 8 Then .NumberFormat = PCT_FMT
            ' Borders only on A, D, G, H
            If c = 1 Or c = 4 Or c = 7 Or c = 8 Then
                .Borders(xlEdgeLeft).LineStyle = xlContinuous
                .Borders(xlEdgeRight).LineStyle = xlContinuous
                .Borders(xlEdgeTop).LineStyle = xlContinuous
                .Borders(xlEdgeBottom).LineStyle = xlContinuous
            End If
        End With
    Next c
End Sub
