       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTINQ.
      *> Account inquiry. Arg: account id. Writes the matching 96-byte
      *> record to OUTFILE. RC 0 found, 4 not found, 8 file error.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCT-FILE ASSIGN TO ACCTFILE
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-FS.
           SELECT OUT-FILE ASSIGN TO OUTFILE
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-OFS.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCT-FILE.
       COPY ACCTREC.
       FD  OUT-FILE.
       01  OUT-REC                 PIC X(96).
       WORKING-STORAGE SECTION.
       01  WS-FS                   PIC XX.
       01  WS-OFS                  PIC XX.
       01  WS-KEY                  PIC X(10).
       01  WS-EOF                  PIC X VALUE "N".
       01  WS-FOUND                PIC X VALUE "N".
       PROCEDURE DIVISION.
           ACCEPT WS-KEY FROM COMMAND-LINE
           OPEN INPUT ACCT-FILE
           IF WS-FS NOT = "00"
               MOVE 8 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM UNTIL WS-EOF = "Y" OR WS-FOUND = "Y"
               READ ACCT-FILE
                   AT END MOVE "Y" TO WS-EOF
                   NOT AT END
                       IF ACCT-ID = WS-KEY
                           MOVE "Y" TO WS-FOUND
                       END-IF
               END-READ
           END-PERFORM
           IF WS-FOUND = "Y"
               OPEN OUTPUT OUT-FILE
               MOVE ACCT-REC TO OUT-REC
               WRITE OUT-REC
               CLOSE OUT-FILE
               MOVE 0 TO RETURN-CODE
           ELSE
               MOVE 4 TO RETURN-CODE
           END-IF
           CLOSE ACCT-FILE
           STOP RUN.
