       IDENTIFICATION DIVISION.
       PROGRAM-ID. POLINQ.
      *> Policy inquiry. Arg: policy id. Writes the matching 65-byte
      *> record to OUTFILE. RC 0 found, 4 not found, 8 file error.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT POL-FILE ASSIGN TO POLFILE
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-FS.
           SELECT OUT-FILE ASSIGN TO OUTFILE
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-OFS.
       DATA DIVISION.
       FILE SECTION.
       FD  POL-FILE.
       COPY POLREC.
       FD  OUT-FILE.
       01  OUT-REC                 PIC X(65).
       WORKING-STORAGE SECTION.
       01  WS-FS                   PIC XX.
       01  WS-OFS                  PIC XX.
       01  WS-KEY                  PIC X(12).
       01  WS-EOF                  PIC X VALUE "N".
       01  WS-FOUND                PIC X VALUE "N".
       PROCEDURE DIVISION.
           ACCEPT WS-KEY FROM COMMAND-LINE
           OPEN INPUT POL-FILE
           IF WS-FS NOT = "00"
               MOVE 8 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM UNTIL WS-EOF = "Y" OR WS-FOUND = "Y"
               READ POL-FILE
                   AT END MOVE "Y" TO WS-EOF
                   NOT AT END
                       IF POL-ID = WS-KEY
                           MOVE "Y" TO WS-FOUND
                       END-IF
               END-READ
           END-PERFORM
           IF WS-FOUND = "Y"
               OPEN OUTPUT OUT-FILE
               MOVE POL-REC TO OUT-REC
               WRITE OUT-REC
               CLOSE OUT-FILE
               MOVE 0 TO RETURN-CODE
           ELSE
               MOVE 4 TO RETURN-CODE
           END-IF
           CLOSE POL-FILE
           STOP RUN.
